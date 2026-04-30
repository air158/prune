from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
import os

import frontmatter


@dataclass
class Skill:
    name: str
    path: str
    location: str          # active | staging | deprecated | root
    status: str
    description: Optional[str]
    total_calls: Optional[int]
    success_count: Optional[int]
    last_called: Optional[date]
    mtime: datetime
    has_fitness_data: bool
    used_by: list[str] = field(default_factory=list)


def _get_location(skill_md: Path, skills_dir: Path) -> str:
    try:
        rel = skill_md.relative_to(skills_dir)
    except ValueError:
        return "root"
    first = rel.parts[0] if rel.parts else ""
    if first in ("active", "staging", "deprecated"):
        return first
    return "root"


def _parse_skill(skill_md: Path, skills_dir: Path) -> Optional[Skill]:
    try:
        post = frontmatter.load(str(skill_md))
    except Exception:
        return None

    meta = post.metadata
    lifecycle = meta.get("lifecycle", {}) or {}
    status = lifecycle.get("status", "unknown")
    description = meta.get("description") or None
    fitness = lifecycle.get("fitness", {}) or {}
    used_by = lifecycle.get("used_by") or []

    has_fitness = bool(fitness)
    total_calls = fitness.get("total_calls")
    success_count = fitness.get("success_count")

    last_called: Optional[date] = None
    last_called_raw = fitness.get("last_called")
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
        location=_get_location(skill_md, skills_dir),
        status=str(status),
        description=description,
        total_calls=int(total_calls) if total_calls is not None else None,
        success_count=int(success_count) if success_count is not None else None,
        last_called=last_called,
        mtime=mtime,
        has_fitness_data=has_fitness,
        used_by=list(used_by) if used_by else [],
    )


def get_skills_root(skills_dir: Optional[str] = None) -> Path:
    if skills_dir:
        return Path(skills_dir).expanduser()
    return Path("~/.hermes/skills/").expanduser()


def load_registry(skills_dir: Optional[str] = None) -> tuple[list[Skill], list[str]]:
    root = get_skills_root(skills_dir)

    if not root.exists():
        return [], []

    skills: list[Skill] = []
    warnings: list[str] = []

    for skill_md in root.rglob("SKILL.md"):
        # Skip deprecated skills in health check
        if "deprecated" in skill_md.parts:
            continue
        skill = _parse_skill(skill_md, root)
        if skill is None:
            warnings.append(f"Skipped {skill_md} (malformed frontmatter)")
        else:
            skills.append(skill)

    return skills, warnings


def find_skill(skills_dir: Optional[str], skill_name: str) -> Optional[Skill]:
    """Locate a skill by name anywhere in the registry, including category subdirectories."""
    root = get_skills_root(skills_dir)

    for skill_md in root.rglob("SKILL.md"):
        if skill_md.parent.name == skill_name:
            return _parse_skill(skill_md, root)

    return None
