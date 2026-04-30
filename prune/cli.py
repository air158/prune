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
    table.add_column("Location")
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
            skill.location,
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


def cmd_update_fitness(args: argparse.Namespace) -> None:
    from prune.fitness import cmd_update_fitness as _run
    _run(
        skills_dir=args.dir,
        skill_name=args.skill,
        result=getattr(args, "result", None),
        calls=getattr(args, "calls", 0) or 0,
        success=getattr(args, "success", 0) or 0,
        no_git=args.no_git,
    )


def cmd_deprecate(args: argparse.Namespace) -> None:
    from prune.lifecycle import cmd_deprecate as _run
    _run(
        skills_dir=args.dir,
        skill_name=args.skill,
        reason=args.reason,
        successor=getattr(args, "successor", None),
        yes=args.yes,
        no_git=args.no_git,
    )


def cmd_promote(args: argparse.Namespace) -> None:
    from prune.lifecycle import cmd_promote as _run
    _run(
        skills_dir=args.dir,
        skill_name=args.skill,
        yes=args.yes,
        no_git=args.no_git,
    )


def cmd_similarity_check(args: argparse.Namespace) -> None:
    from prune.similarity import cmd_similarity_check as _run
    _run(
        skills_dir=args.dir,
        skill_name=args.skill,
        description=getattr(args, "description", None),
        threshold=args.threshold,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prune",
        description="Skill lifecycle manager for Hermes Agent",
    )
    sub = parser.add_subparsers(dest="command")

    # ── check ──────────────────────────────────────────────────────────────
    p_check = sub.add_parser("check", help="Scan registry and show fitness report")
    p_check.add_argument("--dir", metavar="PATH",
                         help="Skills directory (default: ~/.hermes/skills/)")

    # ── update-fitness ─────────────────────────────────────────────────────
    p_uf = sub.add_parser("update-fitness", help="Record a session result for a skill")
    p_uf.add_argument("skill", help="Skill name")
    p_uf.add_argument("--result", choices=["success", "failure"],
                      help="Session result (shortcut for --calls 1 --success 0|1)")
    p_uf.add_argument("--calls", type=int, default=0,
                      help="Number of calls to add (default: 0)")
    p_uf.add_argument("--success", type=int, default=0,
                      help="Number of successful calls to add (default: 0)")
    p_uf.add_argument("--dir", metavar="PATH")
    p_uf.add_argument("--no-git", action="store_true",
                      help="Skip git commit")

    # ── deprecate ──────────────────────────────────────────────────────────
    p_dep = sub.add_parser("deprecate", help="Archive a skill")
    p_dep.add_argument("skill", help="Skill name")
    p_dep.add_argument("--reason", required=True,
                       choices=["cold", "low-utility", "merged", "superseded", "security"])
    p_dep.add_argument("--successor", metavar="SKILL",
                       help="Name of the skill that replaces this one")
    p_dep.add_argument("--yes", "-y", action="store_true",
                       help="Skip confirmation prompt")
    p_dep.add_argument("--dir", metavar="PATH")
    p_dep.add_argument("--no-git", action="store_true")

    # ── promote ────────────────────────────────────────────────────────────
    p_pro = sub.add_parser("promote", help="Move a staging skill to active")
    p_pro.add_argument("skill", help="Skill name")
    p_pro.add_argument("--yes", "-y", action="store_true")
    p_pro.add_argument("--dir", metavar="PATH")
    p_pro.add_argument("--no-git", action="store_true")

    # ── similarity-check ───────────────────────────────────────────────────
    p_sim = sub.add_parser("similarity-check",
                           help="Check if a skill name/description overlaps with existing skills")
    p_sim.add_argument("skill", help="New skill name to check")
    p_sim.add_argument("--description", "-d", metavar="TEXT",
                       help="Description of the new skill")
    p_sim.add_argument("--threshold", type=float, default=0.85,
                       help="Cosine similarity threshold (default: 0.85)")
    p_sim.add_argument("--dir", metavar="PATH")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "check": cmd_check,
        "update-fitness": cmd_update_fitness,
        "deprecate": cmd_deprecate,
        "promote": cmd_promote,
        "similarity-check": cmd_similarity_check,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)
