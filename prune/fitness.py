from datetime import date
from pathlib import Path
from typing import Optional

import frontmatter

from prune.git_ops import git_commit, is_git_repo, GitError


def update_fitness(
    skill_md: Path,
    calls_delta: int,
    success_delta: int,
) -> dict:
    """Update lifecycle.fitness in SKILL.md and return the new fitness state."""
    post = frontmatter.load(str(skill_md))
    meta = post.metadata

    lifecycle = meta.setdefault("lifecycle", {})
    if not isinstance(lifecycle, dict):
        lifecycle = {}
        meta["lifecycle"] = lifecycle

    fitness = lifecycle.setdefault("fitness", {})
    if not isinstance(fitness, dict):
        fitness = {}
        lifecycle["fitness"] = fitness

    total = (fitness.get("total_calls") or 0) + calls_delta
    success = (fitness.get("success_count") or 0) + success_delta
    total = max(total, 0)
    success = max(min(success, total), 0)

    fitness["total_calls"] = total
    fitness["success_count"] = success
    fitness["last_called"] = date.today().isoformat()
    fitness["success_rate"] = round(success / total, 2) if total > 0 else 0.0
    fitness["utility_score"] = round(success / total, 2) if total > 0 else 0.0

    post.metadata = meta
    with open(str(skill_md), "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    return dict(fitness)


def cmd_update_fitness(
    skills_dir: Optional[str],
    skill_name: str,
    result: Optional[str],
    calls: int,
    success: int,
    no_git: bool,
) -> None:
    from prune.registry import get_skills_root, find_skill
    from rich.console import Console

    console = Console()
    root = get_skills_root(skills_dir)
    skill = find_skill(skills_dir, skill_name)

    if skill is None:
        console.print(f"[red]Skill '{skill_name}' not found in {root}[/red]")
        raise SystemExit(1)

    # --result is a shortcut for --calls 1 --success 0|1
    if result == "success":
        calls, success = 1, 1
    elif result == "failure":
        calls, success = 1, 0

    new_fitness = update_fitness(Path(skill.path), calls, success)

    rate = new_fitness.get("success_rate", 0)
    total = new_fitness.get("total_calls", 0)
    console.print(f"[green]Updated[/green] {skill_name}: calls={total} rate={rate:.2f}")

    if not no_git:
        if not is_git_repo(root):
            console.print(
                "[yellow]⚠ Skills directory is not a git repo. "
                "Run 'git init' there to enable audit trail. "
                "Skipping commit.[/yellow]"
            )
            return
        try:
            msg = f"fitness({skill_name}): calls={total} rate={rate:.2f}"
            git_commit(root, msg, [skill.path])
            console.print(f"[dim]git: {msg}[/dim]")
        except GitError as e:
            console.print(f"[yellow]⚠ Git commit failed: {e}[/yellow]")
