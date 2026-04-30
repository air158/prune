"""
Unit tests for scorer.py — verifies that the recommendation logic is correct.
Test cases are taken directly from doc/02-system-design.md Eval section.
"""

import pytest
from datetime import date, datetime, timezone, timedelta

from prune.registry import Skill
from prune.scorer import recommend, Recommendation


def make_skill(
    name: str,
    total_calls: int,
    success_count: int,
    cold_days: int,
    status: str = "active",
) -> Skill:
    last_called = date.today() - timedelta(days=cold_days)
    mtime = datetime.now(tz=timezone.utc) - timedelta(days=cold_days)
    return Skill(
        name=name,
        path=f"/fake/{name}/SKILL.md",
        location="active",
        status=status,
        description=None,
        total_calls=total_calls,
        success_count=success_count,
        last_called=last_called,
        mtime=mtime,
        has_fitness_data=True,
    )


# ── 来自设计文档的测试用例 ───────────────────────────────────────────────────
# doc/02-system-design.md → Eval → 层一：Delete 机制正确性测试

@pytest.mark.parametrize("skill,expected", [
    # 应该死的
    (make_skill("cold-skill",    total_calls=50,  success_count=43, cold_days=90), Recommendation.COLD),
    (make_skill("useless-skill", total_calls=100, success_count=15, cold_days=5),  Recommendation.LOW_UTILITY),

    # 调用次数不足 → 不判定，等数据积累
    (make_skill("new-bad-skill", total_calls=10,  success_count=1,  cold_days=3),  Recommendation.INVESTIGATE),

    # 应该活的
    (make_skill("healthy-skill", total_calls=500, success_count=440, cold_days=2), Recommendation.KEEP),
    (make_skill("rare-skill",    total_calls=25,  success_count=20,  cold_days=45), Recommendation.KEEP),

    # 边界：cold_days=59（刚好低于阈值），utility=0.31（刚好高于阈值）→ KEEP
    (make_skill("borderline-keep", total_calls=20, success_count=7, cold_days=59), Recommendation.KEEP),

    # 边界：cold_days=60（达到阈值）→ COLD
    (make_skill("borderline-cold", total_calls=20, success_count=7, cold_days=60), Recommendation.COLD),

    # staging 状态 → 永远 INVESTIGATE
    (make_skill("staging-skill", total_calls=80, success_count=70, cold_days=1, status="staging"), Recommendation.INVESTIGATE),
])
def test_recommend(skill, expected):
    assert recommend(skill) == expected


def test_cold_wins_over_low_utility():
    """一个 skill 同时冷 AND utility 低 → 应该被判为 COLD（冷优先）"""
    skill = make_skill("double-bad", total_calls=50, success_count=5, cold_days=90)
    assert recommend(skill) == Recommendation.COLD


def test_no_fitness_data_not_condemned():
    """没有 fitness 数据的 skill → 调用次数视为 0 → INVESTIGATE，不被自动淘汰"""
    skill = Skill(
        name="uninstrumented",
        path="/fake/uninstrumented/SKILL.md",
        location="root",
        status="active",
        description=None,
        total_calls=None,
        success_count=None,
        last_called=None,
        mtime=datetime.now(tz=timezone.utc) - timedelta(days=200),
        has_fitness_data=False,
    )
    # mtime 是 200 天前，如果 total_calls=None 被当做 0，应该 INVESTIGATE 而不是 COLD
    assert recommend(skill) == Recommendation.INVESTIGATE
