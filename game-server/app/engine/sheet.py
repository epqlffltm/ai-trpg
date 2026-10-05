# game-server/app/engine/sheet.py

"""
캐릭터 시트의 모양과, 시트가 규칙에 맞는지 보는 방법.

시트는 캐릭터의 숫자다. 능력치의 점수와 최대 HP 가 있다. 이름과 설명(글)은 시트가 아니다.

모양만으로는 맞는 시트인지 알 수 없다. "근력 14"가 맞는지는 규칙에 근력이 있는지, 14 가 범위 안인지에 달렸다.
그래서 둘로 나눈다.
  - 모양(Sheet): 규칙을 몰라도 볼 수 있는 것. 입력을 받을 때 검사한다.
  - 맞음(fits): 규칙과 견주어야 알 수 있는 것. 규칙이 정해진 때(게시할 때)에 검사한다.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.engine.ruleset import RULESET_MAX_ABILITIES, RULESET_MAX_NUMBER, Key, Ruleset

# 최대 HP 가 가질 수 있는 가장 큰 값
SHEET_MAX_HP = 999

Score = Annotated[int, Field(ge=0, le=RULESET_MAX_NUMBER)]


class Sheet(BaseModel):
    """캐릭터 시트 하나."""

    model_config = ConfigDict(extra='forbid')

    # 능력치의 점수. 능력치의 이름표(규칙의 Ability.key)에서 점수로 간다. 예: {'str': 14, 'dex': 12}
    abilities: Annotated[dict[Key, Score], Field(max_length=RULESET_MAX_ABILITIES)]
    # 최대 HP. 규칙에서 계산하지 않고 만든 사람이 직접 적는다
    max_hp: Annotated[int, Field(ge=1, le=SHEET_MAX_HP)]


def has_exact_abilities(ruleset: Ruleset, sheet: Sheet) -> bool:
    """시트가 규칙의 능력치를 빠짐없이, 그리고 그것만 갖고 있는가."""
    return set(sheet.abilities) == {ability.key for ability in ruleset.abilities}


def has_scores_in_range(ruleset: Ruleset, sheet: Sheet) -> bool:
    """시트의 점수가 모두 규칙이 정한 범위 안인가."""
    return all(ruleset.score_min <= score <= ruleset.score_max for score in sheet.abilities.values())


def fits(ruleset: Ruleset, sheet: Sheet) -> bool:
    """시트가 이 규칙에 맞는가."""
    return has_exact_abilities(ruleset, sheet) and has_scores_in_range(ruleset, sheet)
