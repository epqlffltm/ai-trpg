# trpg-server/app/engine/item_effects.py

"""
효과 목록(#800). 소모품을 썼을 때 대상에게 일어나는 일들을 데이터로 적는다.

효과마다 엔진의 코드는 한 번만 있고(app/rounds/item_actions.py), 물건은 그 조합이다. 차례대로 실행한다.
  - heal: 등급(룰북의 magnitudes)만큼 HP 를 되돌린다. 몬스터에게는 회복이 없다.
  - cure: 적은 부상들(룰북의 부상의 이름표)을 푼다. 짧은 것과 오래 가는 것만 푼다(결손은 못 푼다).
  - damage: 등급만큼 피해를 준다. 인물과 몬스터에게는 방어와 세이브가 치기와 같다.
  - injure: 부상 하나를 입힌다. 짧은 것, 오래 가는 것, 결손 모두 된다. 몬스터는 그 성질에 면역이면 입지 않는다.
한 물건에 회복과 피해를 함께 적지 않는다. 회복, 풀기, 피해는 한 번씩이다. 입히기는 여럿이 된다.

모르는 종류는 저장할 때(이 모양) 막는다. 등급과 부상이 룰북에 있는지는 게시할 때 본다(시나리오의 게시).
엔진만 실행한다. 서술이 무엇을 쓰든 상태는 이 효과로만 바뀐다.
"""

import enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.engine.ruleset import Key

# 물건 하나의 효과 수
ITEM_MAX_EFFECTS = 5
# 풀기 하나가 푸는 부상의 수
EFFECT_MAX_CURES = 5


class EffectKind(enum.StrEnum):
    """효과의 종류."""

    HEAL = 'heal'
    CURE = 'cure'
    DAMAGE = 'damage'
    INJURE = 'injure'


# 대상에게 해로운 효과. 동료에게 쓰려면 동의가 있어야 한다(#803 전에는 막는다)
HARMFUL = frozenset({EffectKind.DAMAGE, EffectKind.INJURE})
# 한 물건에 한 번만 적는 효과
ONCE = frozenset({EffectKind.HEAL, EffectKind.CURE, EffectKind.DAMAGE})


def reject_repeated_injuries(keys: list[str]) -> list[str]:
    """같은 부상을 두 번 풀지 않는다."""
    if len(set(keys)) != len(keys):
        raise ValueError('같은 부상을 두 번 풉니다.')
    return keys


class HealEffect(BaseModel):
    """HP 를 등급(magnitude)만큼 되돌린다."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal[EffectKind.HEAL]
    magnitude: Key


class CureEffect(BaseModel):
    """적은 부상들(injuries)을 푼다. 대상이 입고 있지 않으면 아무 일도 없다."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal[EffectKind.CURE]
    injuries: Annotated[
        list[Key], Field(min_length=1, max_length=EFFECT_MAX_CURES), AfterValidator(reject_repeated_injuries)
    ]


class DamageEffect(BaseModel):
    """등급(magnitude)만큼 피해를 준다."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal[EffectKind.DAMAGE]
    magnitude: Key


class InjureEffect(BaseModel):
    """부상 하나(injury)를 입힌다. 이미 입고 있으면 또 입히지 않는다."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal[EffectKind.INJURE]
    injury: Key


Effect = Annotated[HealEffect | CureEffect | DamageEffect | InjureEffect, Field(discriminator='kind')]


def reject_conflicting_effects(effects: list) -> list:
    """회복과 피해를 함께 적지 않는다. 회복, 풀기, 피해는 한 번씩, 같은 부상을 두 번 입히지 않는다."""
    kinds = [effect.kind for effect in effects]
    if EffectKind.HEAL in kinds and EffectKind.DAMAGE in kinds:
        raise ValueError('회복(heal)과 피해(damage)를 한 물건에 함께 적지 않습니다.')
    if any(kinds.count(kind) > 1 for kind in ONCE):
        raise ValueError('회복, 풀기, 피해는 한 물건에 한 번씩만 적습니다.')
    injured = [effect.injury for effect in effects if effect.kind == EffectKind.INJURE]
    if len(set(injured)) != len(injured):
        raise ValueError('같은 부상을 두 번 입힙니다.')
    return effects


Effects = Annotated[list[Effect], Field(max_length=ITEM_MAX_EFFECTS), AfterValidator(reject_conflicting_effects)]


def is_harmful(effects: list) -> bool:
    """대상에게 해로운 효과(피해, 부상)가 있는가."""
    return any(effect.kind in HARMFUL for effect in effects)


def first_of(effects: list, kind: EffectKind):
    """그 종류의 첫 효과. 없으면 None."""
    return next((effect for effect in effects if effect.kind == kind), None)
