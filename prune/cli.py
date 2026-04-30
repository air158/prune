import argparse
import sys

from rich.console import Console
from rich.table import Table
from rich import box

from prune.registry import load_registry
from prune.scorer import recommend, utility_score, cold_days, SORT_ORDER, Recommendation

console = Console()

REC_STYLE = {
    Recommendation.KEEP: "green",
    Recommendation.COLD: "cyan",
    Recommendation.LOW_UTILITY: "yellow",
    Recommendation.INVESTIGATE: "dim",
}


def cmd_check(args: argparse.Namespace) -> None:
    skills_dir = getattr(args, "dir", None)
    skills, warnings = load_registry(skills_dir)

    if not skills and not warnings:
        console.print("[dim]Registry is empty.[/dim]")
        return

    scored = sorted(skills, key=lambda s: SORT_ORDER[recommend(s)])

    table = Table(box=box.SIMPLE_HEAD, show_footer=False)
    table.add_column("Skill", style="bold")
    table.add_column("Status")
    table.add_column("Utility", justify="right")
    table.add_column("Cold Days", justify="right")
    table.add_column("Data Source")
    table.add_column("Recommendation")

    for skill in scored:
        rec = recommend(skill)
        score = utility_score(skill)
        cd = cold_days(skill)
        style = REC_STYLE[rec]
        data_source = "fitness" if skill.has_fitness_data else "mtime"
        utility_str = f"{score:.2f}" if score is not None else "—"

        table.add_row(
            skill.name,
            skill.status,
            utility_str,
            str(cd),
            data_source,
            f"[{style}]{rec.value}[/{style}]",
        )

    console.print(table)

    uninstrumented = sum(1 for s in skills if not s.has_fitness_data)
    if uninstrumented:
        console.print(
            f"\n[dim]ℹ {uninstrumented} skill(s) have no fitness data. "
            "Run [bold]prune update-fitness[/bold] after each session to start tracking.[/dim]"
        )

    if warnings:
        console.print()
        for w in warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="prune",
        description="Skill lifecycle manager for Hermes Agent",
    )
    sub = parser.add_subparsers(dest="command")

    check_parser = sub.add_parser("check", help="Scan registry and show fitness report")
    check_parser.add_argument(
        "--dir",
        metavar="PATH",
        help="Path to skills directory (default: ~/.hermes/skills/)",
    )

    args = parser.parse_args()

    if args.command == "check":
        cmd_check(args)
    else:
        parser.print_help()
        sys.exit(1)
