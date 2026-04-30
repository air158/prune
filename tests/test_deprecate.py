"""
Integration tests for deprecate command — dependency safety check.
doc/02-system-design.md → Eval → 依赖安全测试
"""

import textwrap
import pytest
from pathlib import Path

from prune.registry import find_skill
from prune.lifecycle import cmd_deprecate


def write_skill(skills_dir: Path, name: str, used_by: list[str] | None = None) -> Path:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"

    used_by_yaml = ""
    if used_by:
        items = "\n".join(f"    - {s}" for s in used_by)
        used_by_yaml = f"  used_by:\n{items}\n"

    skill_md.write_text(textwrap.dedent(f"""\
        ---
        name: {name}
        description: Test skill {name}
        lifecycle:
          status: active
        {used_by_yaml}---

        Test skill body.
        """), encoding="utf-8")
    return skill_md


def test_deprecate_blocked_by_dependency(tmp_path):
    """
    http-client が web-search に依存されている → deprecate は blocked されるべき
    doc: assert deprecate("http-client") == "blocked"
    """
    write_skill(tmp_path, "http-client", used_by=["web-search", "api-caller"])
    write_skill(tmp_path, "web-search")
    write_skill(tmp_path, "api-caller")

    with pytest.raises(SystemExit) as exc:
        cmd_deprecate(
            skills_dir=str(tmp_path),
            skill_name="http-client",
            reason="cold",
            successor=None,
            yes=True,
            no_git=True,
        )
    assert exc.value.code == 1


def test_deprecate_succeeds_when_no_dependencies(tmp_path):
    """
    used_by が空 → deprecate は成功し、deprecated/YYYY-MM/ に移動されるべき
    """
    write_skill(tmp_path, "orphan-skill", used_by=[])

    cmd_deprecate(
        skills_dir=str(tmp_path),
        skill_name="orphan-skill",
        reason="cold",
        successor=None,
        yes=True,
        no_git=True,
    )

    # 元の場所には存在しない
    assert not (tmp_path / "orphan-skill").exists()

    # deprecated/YYYY-MM/ に移動されている
    deprecated_dirs = list((tmp_path / "deprecated").rglob("SKILL.md"))
    assert len(deprecated_dirs) == 1
    assert deprecated_dirs[0].parent.name == "orphan-skill"


def test_deprecate_writes_retire_md(tmp_path):
    """RETIRE.md が正しく書かれているか"""
    write_skill(tmp_path, "retiring-skill")

    cmd_deprecate(
        skills_dir=str(tmp_path),
        skill_name="retiring-skill",
        reason="low-utility",
        successor="better-skill",
        yes=True,
        no_git=True,
    )

    retire_files = list((tmp_path / "deprecated").rglob("RETIRE.md"))
    assert len(retire_files) == 1

    content = retire_files[0].read_text()
    assert "reason: low-utility" in content
    assert "successor: better-skill" in content
    assert "retired_at:" in content


def test_deprecate_already_deprecated(tmp_path):
    """すでに deprecated なスキルを再度 deprecate しようとしても無害に終了"""
    dep_dir = tmp_path / "deprecated" / "2026-04" / "old-skill"
    dep_dir.mkdir(parents=True)
    (dep_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: old-skill
        lifecycle:
          status: deprecated
        ---
        """), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        cmd_deprecate(
            skills_dir=str(tmp_path),
            skill_name="old-skill",
            reason="cold",
            successor=None,
            yes=True,
            no_git=True,
        )
    assert exc.value.code == 0
