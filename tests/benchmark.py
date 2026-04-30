"""
prune benchmark — 两项指标：
  1. 分类准确率：precision / recall / F1（scorer 对已知标签数据的表现）
  2. 扫描性能：prune check 在不同规模下的耗时

用法：
  python tests/benchmark.py
  python tests/benchmark.py --no-perf      # 只跑准确率
  python tests/benchmark.py --no-accuracy  # 只跑性能
"""

import argparse
import random
import tempfile
import time
import textwrap
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

from prune.registry import Skill
from prune.scorer import recommend, Recommendation

console = Console()


# ── 合成数据生成 ─────────────────────────────────────────────────────────────

def make_skill(name, total_calls, success_count, cold_days_val, status="active") -> Skill:
    last_called = date.today() - timedelta(days=cold_days_val)
    mtime = datetime.now(tz=timezone.utc) - timedelta(days=cold_days_val)
    return Skill(
        name=name, path=f"/bench/{name}/SKILL.md",
        location="active", status=status, description=None,
        total_calls=total_calls, success_count=success_count,
        last_called=last_called, mtime=mtime, has_fitness_data=True,
    )


def labeled_dataset() -> list[tuple[Skill, str]]:
    """
    Returns (skill, true_label) pairs.
    true_label: "keep" | "cold" | "low_utility" | "investigate"
    """
    random.seed(0)
    cases = []

    # ── 明确应该 KEEP ─────────────────────────────────────────────
    for i in range(30):
        calls = random.randint(50, 600)
        success = int(calls * random.uniform(0.65, 0.98))
        cold = random.randint(0, 30)
        cases.append((make_skill(f"healthy-{i}", calls, success, cold), "keep"))

    # ── 明确应该 COLD ─────────────────────────────────────────────
    for i in range(15):
        calls = random.randint(25, 200)
        success = int(calls * random.uniform(0.5, 0.95))
        cold = random.randint(61, 180)   # > 60 天，超过阈值
        cases.append((make_skill(f"cold-{i}", calls, success, cold), "cold"))

    # ── 明确应该 LOW_UTILITY ──────────────────────────────────────
    for i in range(15):
        calls = random.randint(25, 200)
        success = int(calls * random.uniform(0.02, 0.25))  # utility < 0.30
        cold = random.randint(0, 30)
        cases.append((make_skill(f"low-{i}", calls, success, cold), "low_utility"))

    # ── 应该 INVESTIGATE（调用不足）──────────────────────────────
    for i in range(20):
        calls = random.randint(0, 19)
        success = int(calls * random.uniform(0, 1))
        cold = random.randint(0, 90)
        cases.append((make_skill(f"new-{i}", calls, success, cold), "investigate"))

    # ── staging 状态 → 永远 INVESTIGATE ──────────────────────────
    for i in range(10):
        calls = random.randint(30, 200)
        success = int(calls * random.uniform(0.5, 0.95))
        cases.append((make_skill(f"staging-{i}", calls, success, 5, status="staging"), "investigate"))

    return cases


REC_TO_LABEL = {
    Recommendation.KEEP: "keep",
    Recommendation.COLD: "cold",
    Recommendation.LOW_UTILITY: "low_utility",
    Recommendation.INVESTIGATE: "investigate",
}


def run_accuracy_benchmark() -> None:
    console.print("\n[bold]Benchmark 1: Classification accuracy[/bold]\n")

    dataset = labeled_dataset()
    labels = ["keep", "cold", "low_utility", "investigate"]

    # confusion matrix[true][pred]
    confusion: dict[str, dict[str, int]] = {l: {l2: 0 for l2 in labels} for l in labels}

    for skill, true_label in dataset:
        pred_label = REC_TO_LABEL[recommend(skill)]
        confusion[true_label][pred_label] += 1

    # Per-class precision / recall / F1
    metrics = []
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in labels if other != label)
        fn = sum(confusion[label][other] for other in labels if other != label)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        support   = sum(confusion[label].values())
        metrics.append((label, precision, recall, f1, support))

    # Overall accuracy
    correct = sum(confusion[l][l] for l in labels)
    total   = len(dataset)
    accuracy = correct / total

    table = Table(box=box.SIMPLE_HEAD, title=f"Results on {total} labeled samples")
    table.add_column("Label")
    table.add_column("Precision", justify="right")
    table.add_column("Recall", justify="right")
    table.add_column("F1", justify="right")
    table.add_column("Support", justify="right")

    for label, p, r, f1, sup in metrics:
        color = "green" if f1 >= 0.9 else "yellow" if f1 >= 0.7 else "red"
        table.add_row(label, f"{p:.2f}", f"{r:.2f}", f"[{color}]{f1:.2f}[/{color}]", str(sup))

    table.add_section()
    macro_f1 = sum(m[3] for m in metrics) / len(metrics)
    color = "green" if macro_f1 >= 0.9 else "yellow" if macro_f1 >= 0.7 else "red"
    table.add_row(
        "[bold]macro avg[/bold]", "", "", f"[{color}][bold]{macro_f1:.2f}[/bold][/{color}]",
        str(total),
    )
    console.print(table)
    console.print(f"Overall accuracy: [bold]{accuracy:.1%}[/bold] ({correct}/{total})\n")

    # 打印混淆矩阵（仅非零部分）
    console.print("[dim]Confusion matrix (row=true, col=predicted):[/dim]")
    cm_table = Table(box=box.SIMPLE, show_header=True)
    cm_table.add_column("true \\ pred", style="dim")
    for label in labels:
        cm_table.add_column(label[:12], justify="right")
    for true_label in labels:
        row = [true_label]
        for pred_label in labels:
            v = confusion[true_label][pred_label]
            if v == 0:
                row.append("[dim]0[/dim]")
            elif true_label == pred_label:
                row.append(f"[green]{v}[/green]")
            else:
                row.append(f"[red]{v}[/red]")
        cm_table.add_row(*row)
    console.print(cm_table)


# ── 性能 benchmark ────────────────────────────────────────────────────────────

def write_synthetic_registry(tmp_dir: Path, n: int) -> None:
    for i in range(n):
        skill_dir = tmp_dir / f"skill-{i:04d}"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(textwrap.dedent(f"""\
            ---
            name: skill-{i:04d}
            description: Synthetic skill number {i}
            lifecycle:
              status: active
              fitness:
                total_calls: {random.randint(5, 500)}
                success_count: {random.randint(0, 200)}
                last_called: {(date.today() - timedelta(days=random.randint(0, 120))).isoformat()}
            ---
            Synthetic skill body.
            """), encoding="utf-8")


def run_perf_benchmark() -> None:
    from prune.registry import load_registry

    console.print("\n[bold]Benchmark 2: Scan performance[/bold]\n")

    sizes = [50, 200, 500, 1000, 2000]
    table = Table(box=box.SIMPLE_HEAD, title="prune check scan time")
    table.add_column("Skills", justify="right")
    table.add_column("Time (ms)", justify="right")
    table.add_column("Per skill (µs)", justify="right")

    for n in sizes:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_synthetic_registry(tmp_path, n)

            # warm-up
            load_registry(str(tmp_path))

            # timed run (3 iterations, take median)
            times = []
            for _ in range(3):
                t0 = time.perf_counter()
                skills, _ = load_registry(str(tmp_path))
                for s in skills:
                    recommend(s)
                t1 = time.perf_counter()
                times.append(t1 - t0)

            median_ms = sorted(times)[1] * 1000
            per_skill_us = (median_ms / n) * 1000
            color = "green" if median_ms < 500 else "yellow" if median_ms < 2000 else "red"
            table.add_row(str(n), f"[{color}]{median_ms:.0f}[/{color}]", f"{per_skill_us:.0f}")

    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-perf",     action="store_true")
    parser.add_argument("--no-accuracy", action="store_true")
    args = parser.parse_args()

    if not args.no_accuracy:
        run_accuracy_benchmark()
    if not args.no_perf:
        run_perf_benchmark()
