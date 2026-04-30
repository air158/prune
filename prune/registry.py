from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
import os

import frontmatter


@dataclass
class Skill:
    name: str
    path: str
    status: str
    total_calls: Optional[int]
    success_count: Optional[int]
    last_called: Optional[date]
    mtime: datetime
    has_fitness_data: bool


def _parse_skill(skill_md: Path) -> Optional[Skill]:
    try:
        post = frontmatter.load(str(skill_md))
    except Exception:
        return None

    meta = post.metadata
    lifecycle = meta.get("lifecycle", {}) or {}
    status = lifecycle.get("status", "unknown")
    fitness = lifecycle.get("fitness", {}) or {}

    has_fitness = bool(fitness)
    total_calls = fitness.get("total_calls")
    success_count = fitness.get("success_count")

    last_called_raw = fitness.get("last_called")
    last_called: Optional[date] = None
    if last_called_raw:
        try:
            if isinstance(last_called_raw, date):
                last_called = last_called_raw
            else:
                last_called = date.fromisoformat(str(last_called_raw))
        except ValueError:
            pass

    mtime_ts = os.path.getmtime(str(skill_md))
    mtime = datetime.fromtimestamp(mtime_ts, tz=timezone.utc)

    return Skill(
        name=skill_md.parent.name,
        path=str(skill_md),
        status=str(status),
        total_calls=int(total_calls) if total_calls is not None else None,
        success_count=int(success_count) if success_count is not None else None,
        last_called=last_called,
        mtime=mtime,
        has_fitness_data=has_fitness,
    )


def load_registry(skills_dir: Optional[str] = None) -> tuple[list[Skill], list[str]]:
    if skills_dir is None:
        root = Path("~/.hermes/skills/").expanduser()
    else:
        root = Path(skills_dir).expanduser()

    if not root.exists():
        return [], []

    skills: list[Skill] = []
    warnings: list[str] = []

    for skill_md in root.rglob("SKILL.md"):
        skill = _parse_skill(skill_md)
        if skill is None:
            warnings.append(f"Skipped {skill_md} (malformed frontmatter)")
        else:
            skills.append(skill)

    return skills, warnings
