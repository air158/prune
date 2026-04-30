from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from prune.registry import Skill

COLD_DAYS_THRESHOLD = 60
UTILITY_MIN = 0.30
MIN_CALLS_TO_EVALUATE = 20


class Recommendation(Enum):
    KEEP = "KEEP"
    COLD = "COLD ❄"
    LOW_UTILITY = "LOW_UTILITY ⚠"
    INVESTIGATE = "INVESTIGATE"


SORT_ORDER = {
    Recommendation.LOW_UTILITY: 0,
    Recommendation.COLD: 1,
    Recommendation.INVESTIGATE: 2,
    Recommendation.KEEP: 3,
}


def utility_score(skill: Skill) -> Optional[float]:
    if skill.total_calls is None or skill.total_calls == 0:
        return None
    if skill.success_count is None:
        return None
    return skill.success_count / skill.total_calls


def cold_days(skill: Skill) -> int:
    today = date.today()
    if skill.last_called is not None:
        return (today - skill.last_called).days
    mtime_date = skill.mtime.astimezone().date()
    return (today - mtime_date).days


def recommend(skill: Skill) -> Recommendation:
    if skill.status == "staging":
        return Recommendation.INVESTIGATE

    calls = skill.total_calls or 0
    if calls < MIN_CALLS_TO_EVALUATE:
        return Recommendation.INVESTIGATE

    # COLD check runs before LOW_UTILITY intentionally:
    # a skill that is both cold and low-utility is classified as COLD.
    if cold_days(skill) >= COLD_DAYS_THRESHOLD:
        return Recommendation.COLD

    score = utility_score(skill)
    if score is not None and score < UTILITY_MIN:
        return Recommendation.LOW_UTILITY

    return Recommendation.KEEP
