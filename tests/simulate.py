"""
Ecosystem health simulation — doc/02-system-design.md 层二：生态健康指标测试

用法：
  python tests/simulate.py
  python tests/simulate.py --rounds 10 --skills 50 --sessions-per-round 20

验证：在模拟运行后，生态整体是否向健康方向演化：
  - 平均 utility_score 上升（坏 skill 被识别为淘汰候选）
  - KEEP 比例上升
  - COLD/LOW_UTILITY 都是真正低质量的 skill
"""

import argparse
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta

from rich.console import Console
from rich.table import Table
from rich import box

from prune.registry import Skill
from prune.scorer import recommend, utility_score, Recommendation, COLD_DAYS_THRESHOLD, UTILITY_MIN

console = Console()


@dataclass
class SimSkill:
    name: str
    true_quality: float       # 真实成功率（agent 永远不知道这个数）
    call_weight: float        # 被调用的相对权重
    total_calls: int = 0
    success_count: int = 0
    last_call_day: int = 0    # 最后一次被调用的轮次


def sim_to_skill(s: SimSkill, current_round: int, rounds_total: int) -> Skill:
    """把模拟 skill 转换为 scorer 可以理解的 Skill 对象"""
    days_since_called = (current_round - s.last_call_day) * 3  # 每轮≈3天
    last_called = date.today() - timedelta(days=days_since_called)
    mtime = datetime.now(tz=timezone.utc) - timedelta(days=days_since_called)
    return Skill(
        name=s.name,
        path=f"/sim/{s.name}/SKILL.md",
        location="active",
        status="active",
        description=None,
        total_calls=s.total_calls,
        success_count=s.success_count,
        last_called=last_called,
        mtime=mtime,
        has_fitness_data=s.total_calls > 0,
    )


def build_population(n_skills: int) -> list[SimSkill]:
    skills = []
    # 40% 高质量（应该 KEEP）
    for i in range(int(n_skills * 0.4)):
        skills.append(SimSkill(
            name=f"healthy-{i:02d}",
            true_quality=random.uniform(0.72, 0.97),
            call_weight=3.0,
        ))
    # 30% 中等质量（接近边界）
    for i in range(int(n_skills * 0.3)):
        skills.append(SimSkill(
            name=f"medium-{i:02d}",
            true_quality=random.uniform(0.32, 0.65),
            call_weight=1.5,
        ))
    # 20% 低质量（应该 LOW_UTILITY）
    # call_weight 调高，确保能积累足够调用次数触发评估
    for i in range(int(n_skills * 0.2)):
        skills.append(SimSkill(
            name=f"low-{i:02d}",
            true_quality=random.uniform(0.05, 0.25),
            call_weight=2.0,
        ))
    # 10% 冷却 skill（质量好但不再被调用，应该 COLD）
    # 曾经活跃（已有 50 次调用记录），后来没人用了
    for i in range(int(n_skills * 0.1)):
        skills.append(SimSkill(
            name=f"cold-{i:02d}",
            true_quality=0.85,
            call_weight=0.0,    # 本轮模拟中永远不被调用
            last_call_day=-30,  # 已经 30 轮（≈90天）没被调用
            total_calls=50,
            success_count=43,
        ))
    return skills


def run_simulation(n_skills: int, n_rounds: int, sessions_per_round: int) -> None:
    random.seed(42)
    skills = build_population(n_skills)

    console.print(f"\n[bold]Ecosystem simulation[/bold]: {n_skills} skills, "
                  f"{n_rounds} rounds × {sessions_per_round} sessions\n")

    rounds_history = []

    for round_num in range(1, n_rounds + 1):
        # 每轮跑 sessions_per_round 个 session，每个 session 随机调用 3-8 个 skill
        callable_skills = [s for s in skills if s.call_weight > 0]
        weights = [s.call_weight for s in callable_skills]

        for _ in range(sessions_per_round):
            n_calls = random.randint(3, min(8, len(callable_skills)))
            called = random.choices(callable_skills, weights=weights, k=n_calls)
            for skill in called:
                skill.total_calls += 1
                if random.random() < skill.true_quality:
                    skill.success_count += 1
                skill.last_call_day = round_num

        # 评分
        skill_objs = [sim_to_skill(s, round_num, n_rounds) for s in skills]
        recs = [recommend(so) for so in skill_objs]

        counts = {r: recs.count(r) for r in Recommendation}
        scored = [so for so in skill_objs if so.total_calls and so.total_calls >= 20]
        avg_utility = (
            sum(utility_score(s) or 0 for s in scored) / len(scored)
            if scored else 0.0
        )

        rounds_history.append({
            "round": round_num,
            "keep": counts[Recommendation.KEEP],
            "cold": counts[Recommendation.COLD],
            "low_utility": counts[Recommendation.LOW_UTILITY],
            "investigate": counts[Recommendation.INVESTIGATE],
            "avg_utility": avg_utility,
        })

    # ── 结果表格 ────────────────────────────────────────────────────────────
    table = Table(box=box.SIMPLE_HEAD, title="Health Metrics per Round")
    table.add_column("Round", justify="right")
    table.add_column("KEEP", justify="right", style="green")
    table.add_column("COLD ❄", justify="right", style="cyan")
    table.add_column("LOW_UTILITY ⚠", justify="right", style="yellow")
    table.add_column("INVESTIGATE", justify="right", style="dim")
    table.add_column("Avg Utility", justify="right")

    for h in rounds_history:
        table.add_row(
            str(h["round"]),
            str(h["keep"]),
            str(h["cold"]),
            str(h["low_utility"]),
            str(h["investigate"]),
            f"{h['avg_utility']:.2f}" if h["avg_utility"] else "—",
        )

    console.print(table)

    # ── 验证 ────────────────────────────────────────────────────────────────
    first = rounds_history[4] if len(rounds_history) >= 5 else rounds_history[0]
    last = rounds_history[-1]

    console.print("\n[bold]Validation[/bold]")

    # 最终轮次的评分结果，按 name 前缀分组
    final_skill_objs = [sim_to_skill(s, n_rounds, n_rounds) for s in skills]
    final_recs = {so.name: recommend(so) for so in final_skill_objs}
    final_utility = {so.name: utility_score(so) for so in final_skill_objs}

    # 低质量 skill 的平均 utility（只算有数据的）
    low_utilities = [
        final_utility[n] for n in final_utility
        if n.startswith("low-") and final_utility[n] is not None
    ]
    keep_utilities = [
        final_utility[n] for n in final_utility
        if n.startswith("healthy-") and final_utility[n] is not None
    ]

    avg_low = sum(low_utilities) / len(low_utilities) if low_utilities else 0.0
    avg_keep = sum(keep_utilities) / len(keep_utilities) if keep_utilities else 0.0

    # 有多少真正低质量 skill 被正确标记为 LOW_UTILITY 或 COLD
    correctly_flagged = sum(
        1 for n, r in final_recs.items()
        if n.startswith("low-") and r in (Recommendation.LOW_UTILITY, Recommendation.COLD)
    )
    cold_correctly_flagged = sum(
        1 for n, r in final_recs.items()
        if n.startswith("cold-") and r == Recommendation.COLD
    )
    # healthy skill 中误报为需要淘汰的数量
    false_positives = sum(
        1 for n, r in final_recs.items()
        if n.startswith("healthy-") and r in (Recommendation.LOW_UTILITY, Recommendation.COLD)
    )

    checks = [
        (
            "KEEP skills have high utility",
            avg_keep >= 0.65,
            f"avg utility of healthy skills = {avg_keep:.2f} (expected ≥0.65)",
        ),
        (
            "LOW_UTILITY skills have low utility",
            avg_low <= 0.30,
            f"avg utility of low-quality skills = {avg_low:.2f} (expected ≤0.30)",
        ),
        (
            "Cold skills are detected",
            cold_correctly_flagged == int(n_skills * 0.1),
            f"{cold_correctly_flagged}/{int(n_skills * 0.1)} cold skills correctly flagged",
        ),
        (
            "Low-utility skills are flagged",
            correctly_flagged >= int(n_skills * 0.1),
            f"{correctly_flagged}/{int(n_skills * 0.2)} low-quality skills flagged",
        ),
        (
            "No false positives on healthy skills",
            false_positives == 0,
            f"{false_positives} healthy skills wrongly flagged",
        ),
    ]

    all_passed = True
    for label, passed, detail in checks:
        icon = "[green]✓[/green]" if passed else "[red]✗[/red]"
        console.print(f"  {icon}  {label}: {detail}")
        if not passed:
            all_passed = False

    console.print()
    if all_passed:
        console.print("[green bold]PASSED[/green bold] — prune correctly identifies sick skills "
                      "and leaves healthy ones alone.")
    else:
        console.print("[red bold]FAILED[/red bold] — some checks did not pass.")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ecosystem health simulation for prune")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--skills", type=int, default=50)
    parser.add_argument("--sessions-per-round", type=int, default=20)
    args = parser.parse_args()

    run_simulation(args.skills, args.rounds, args.sessions_per_round)
