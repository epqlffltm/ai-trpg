# trpg-server/app/engine/item_aids.py

"""
거들기(#802). 물건이 다른 행동의 판정을 거드는 방식을 데이터로 적는다.

물건 하나에 거드는 행동마다 한 줄이다. 한 줄은 어느 행동(act)에, 판정의 보정(bonus)을 얼마나,
쓰면 어떻게 없어지는지(wear)다.
  - act: 치료(treat), 따기(pick), 고치기(repair), 부수기(force), 넘기(cross).
  - bonus: 판정의 보정에 더하는 값. 0 이면 보정 없이 도구로만 쓴다(길이 도구를 요구할 때, 락픽).
  - wear: 굴렸을 때 물건이 어떻게 되나. always(늘 하나 없어짐, 붕대), on_fail(실패하면 부러져 없어짐, 락픽),
    never(없어지지 않음, 공구).
한 물건에 같은 행동을 두 번 적지 않는다. 장비와 소모품 모두 적는다.
행동에 물건을 붙이는 것은 플레이어다(행동의 item). 엔진이 고르지 않는다. 판정을 굴리지 않았으면 물건은 그대로다.

모르는 행동과 방식은 저장할 때(이 모양) 막는다. 엔진만 실행한다(app/rounds/aids.py).
"""

import enum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# 물건 하나의 거들기 수(행동마다 하나)
ITEM_MAX_AIDS = 5
# 거들기의 보정의 끝
AID_MAX_BONUS = 10


class AidAct(enum.StrEnum):
    """거드는 행동."""

    TREAT = 'treat'
    PICK = 'pick'
    REPAIR = 'repair'
    FORCE = 'force'
    CROSS = 'cross'


class AidWear(enum.StrEnum):
    """거든 물건이 굴린 뒤에 어떻게 되나."""

    # 성공하든 실패하든 하나 없어진다(붕대, 의료 키트)
    ALWAYS = 'always'
    # 실패하면 부러져 하나 없어진다(락픽)
    ON_FAIL = 'on_fail'
    # 없어지지 않는다(공구, 밧줄)
    NEVER = 'never'


class ItemAid(BaseModel):
    """물건이 행동 하나(act)를 거드는 방식. 판정에 bonus 를 더하고, 굴린 뒤 wear 대로 된다."""

    model_config = ConfigDict(extra='forbid')

    act: AidAct
    bonus: int = Field(default=0, ge=0, le=AID_MAX_BONUS)
    wear: AidWear = AidWear.NEVER


def reject_repeated_acts(aids: list[ItemAid]) -> list[ItemAid]:
    """한 물건에 같은 행동을 두 번 적지 않는다."""
    acts = [aid.act for aid in aids]
    if len(set(acts)) != len(acts):
        raise ValueError('한 물건에 같은 행동의 거들기를 두 번 적었습니다.')
    return aids


Aids = Annotated[list[ItemAid], Field(max_length=ITEM_MAX_AIDS), AfterValidator(reject_repeated_acts)]


def aid_for(aids: list, act: AidAct):
    """그 행동을 거드는 줄. 없으면 None."""
    return next((aid for aid in aids if aid.act == act), None)


def is_lost(wear: AidWear, success: bool) -> bool:
    """굴린 뒤 물건이 하나 없어지는가. 늘 없어지거나, 실패해서 부러졌다."""
    return wear == AidWear.ALWAYS or (wear == AidWear.ON_FAIL and not success)
