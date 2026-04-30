import shutil
from datetime import date
from pathlib import Path
from typing import Optional

import frontmatter

from prune.git_ops import git_commit, is_git_repo, GitError
from prune.scorer import cold_days, utility_score


VALID_REASONS = ("cold", "low-utility", "merged", "superseded", "security")


def _write_retire_md(retire_path: Path, skill, reason: str, successor: Optional[str]) -> None:
    from prune.scorer import cold_days, utility_score

    u = utility_score(skill)
    cd = cold_days(skill)
    rate = round(skill.success_count / skill.total_calls, 2) if skill.total_calls else None

    successor_line = f"successor: {successor}" if successor else ""

    reason_prose = {
        "cold": f"{cd} days without a call (threshold: 60).",
        "low-utility": f"utility_score {u:.2f} below threshold (0.30)." if u is not None else "utility below threshold.",
        "merged": f"Absorbed into {successor}." if successor else "Merged into a stronger skill.",
        "superseded": f"Replaced by {successor}." if successor else "Superseded by a newer skill.",
        "security": "Retired for security reasons.",
    }.get(reason, reason)

    content = f"""---
retired_at: {date.today().isoformat()}
retired_by: human
reason: {reason}
{successor_line}
---

## Exit reason

{reason_prose}

## Final fitness snapshot

total_calls: {skill.total_calls or 0}
success_rate: {rate if rate is not None else '—'}
utility_score: {f'{u:.2f}' if u is not None else '—'}
cold_days: {cd}
"""
    retire_path.write_text(content.strip() + "\n", encoding="utf-8")


def _set_status(skill_md: Path, new_status: str) -> None:
    post = frontmatter.load(str(skill_md))
    lifecycle = post.metadata.setdefault("lifecycle", {})
    lifecycle["status"] = new_status
    lifecycle["status_changed_at"] = date.today().isoformat()
    with open(str(skill_md), "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))


def cmd_deprecate(
    skills_dir: Optional[str],
    skill_name: str,
    reason: str,
    successor: Optional[str],
    yes: bool,
    no_git: bool,
) -> None:
    from prune.registry import get_skills_root, find_skill
    from rich.console import Console
    import sys

    console = Console()
    root = get_skills_root(skills_dir)
    skill = find_skill(skills_dir, skill_name)

    if skill is None:
        console.print(f"[red]Skill '{skill_name}' not found.[/red]")
        raise SystemExit(1)

    if skill.location == "deprecated":
        console.print(f"[yellow]'{skill_name}' is already deprecated.[/yellow]")
        raise SystemExit(0)

    # Dependency check
    if skill.used_by:
        console.print(f"[red]ERROR: Cannot deprecate '{skill_name}'[/red]")
        console.print("The following skills depend on it:")
        for dep in skill.used_by:
            console.print(f"  - {dep}")
        console.print("\nRemove those dependencies first, or use --cascade (not implemented).")
        raise SystemExit(1)

    # Confirmation
    if not yes:
        console.print(f"[yellow]About to deprecate:[/yellow] {skill_name}")
        console.print(f"  reason: {reason}")
        if successor:
            console.print(f"  successor: {successor}")
        confirm = input("Confirm? [y/N] ").strip().lower()
        if confirm != "y":
            console.print("[dim]Aborted.[/dim]")
            raise SystemExit(0)

    # Move to deprecated/YYYY-MM/
    month = date.today().strftime("%Y-%m")
    dest_dir = root / "deprecated" / month / skill_name
    src_dir = Path(skill.path).parent

    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        shutil.copy2(str(item), str(dest_dir / item.name))

    # Write RETIRE.md
    _write_retire_md(dest_dir / "RETIRE.md", skill, reason, successor)

    # Update status in the copy
    _set_status(dest_dir / "SKILL.md", "deprecated")

    # Remove source
    shutil.rmtree(str(src_dir))

    console.print(f"[green]Deprecated[/green] {skill_name} → deprecated/{month}/{skill_name}/")

    if not no_git:
        if not is_git_repo(root):
            console.print("[yellow]⚠ Not a git repo. Skipping commit.[/yellow]")
            return
        try:
            msg = f"deprecate({skill_name}): reason={reason}"
            git_commit(
                root, msg,
                [str(dest_dir.relative_to(root)), str(src_dir.relative_to(root))],
            )
            console.print(f"[dim]git: {msg}[/dim]")
        except GitError as e:
            console.print(f"[yellow]⚠ Git commit failed: {e}[/yellow]")


def cmd_promote(
    skills_dir: Optional[str],
    skill_name: str,
    yes: bool,
    no_git: bool,
) -> None:
    from prune.registry import get_skills_root, find_skill
    from prune.scorer import SORT_ORDER, Recommendation, recommend
    from rich.console import Console

    console = Console()
    root = get_skills_root(skills_dir)
    skill = find_skill(skills_dir, skill_name)

    if skill is None:
        console.print(f"[red]Skill '{skill_name}' not found.[/red]")
        raise SystemExit(1)

    if skill.location != "staging":
        console.print(f"[yellow]'{skill_name}' is not in staging (location: {skill.location}).[/yellow]")
        raise SystemExit(1)

    src_dir = Path(skill.path).parent
    dest_dir = root / "active" / skill_name

    if dest_dir.exists():
        console.print(f"[red]active/{skill_name} already exists.[/red]")
        raise SystemExit(1)

    # Show fitness summary
    u = utility_score(skill)
    calls = skill.total_calls or 0
    console.print(f"Promoting [bold]{skill_name}[/bold]")
    console.print(f"  calls={calls}  utility={'—' if u is None else f'{u:.2f}'}")

    if not yes:
        confirm = input("Confirm? [y/N] ").strip().lower()
        if confirm != "y":
            console.print("[dim]Aborted.[/dim]")
            raise SystemExit(0)

    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        shutil.copy2(str(item), str(dest_dir / item.name))

    _set_status(dest_dir / "SKILL.md", "active")
    shutil.rmtree(str(src_dir))

    console.print(f"[green]Promoted[/green] {skill_name} → active/{skill_name}/")

    if not no_git:
        if not is_git_repo(root):
            console.print("[yellow]⚠ Not a git repo. Skipping commit.[/yellow]")
            return
        try:
            rate = round(skill.success_count / calls, 2) if calls > 0 and skill.success_count else 0.0
            msg = f"promote({skill_name}): staging→active rate={rate:.2f} calls={calls}"
            git_commit(
                root, msg,
                [str(dest_dir.relative_to(root)), str(src_dir.relative_to(root))],
            )
            console.print(f"[dim]git: {msg}[/dim]")
        except GitError as e:
            console.print(f"[yellow]⚠ Git commit failed: {e}[/yellow]")
