# story-server/app/engine/effects.py

"""
효과를 반영한다(docs/architecture/story.md 의 "효과"). 판과 상태를 받아 반영한 뒤의 상태를 돌려주는 순수 함수다.

이벤트가 열릴 때(on_open)와 선택지를 고를 때 엔진만 반영한다. 모델의 글에는 효과가 없다.
목록은 적힌 차례대로 반영한다. 앞의 효과가 바꾼 상태를 뒤의 효과가 본다.

  affection        target: 인물, amount: ±n   그 인물의 호감도를 바꾼다. 0~100 안으로 자른다
  give_item        target: 물건, amount: n    사용자에게 그 물건을 준다
  take_item        target: 물건, amount: n    사용자에게서 그 물건을 가져간다. 가진 만큼까지다(모자라도 실패가 아니다)
  accompany_start  target: 인물               그 인물과 동행을 시작한다. 이미 동행 중이면 그대로다
  accompany_end    target: 인물               그 인물과 동행을 끝낸다. 동행 중이 아니면 그대로다
  move_to          target: 장소               사용자(와 동행)를 그 장소로 옮긴다. 시간은 흐르지 않는다. 길이 없어도 된다

일러스트를 여는 것은 효과가 아니라 이벤트의 장면의 칸(collectible)이다.
판은 asset 서버가 게시할 때 검사했다(종류마다 쓰는 칸이 채워져 있고, 없는 것을 가리키지 않는다).
"""

import enum
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

# 판 읽기(world.py)가 이벤트와 선택지에 Effect 를 붙인다. 서로 부르지 않게 상태와 판은 타입으로만 가져온다
if TYPE_CHECKING:
    from app.engine.state import StoryState
    from app.engine.world import World

# 호감도의 범위. asset 서버의 AFFECTION_MAX 와 같다
AFFECTION_MIN = 0
AFFECTION_MAX = 100


class EffectKind(enum.StrEnum):
    """효과 하나가 무엇을 바꾸는가. asset 서버의 EffectKind 와 같은 값이다."""

    AFFECTION = 'affection'
    GIVE_ITEM = 'give_item'
    TAKE_ITEM = 'take_item'
    ACCOMPANY_START = 'accompany_start'
    ACCOMPANY_END = 'accompany_end'
    MOVE_TO = 'move_to'


class Effect(BaseModel):
    """효과 하나. amount 는 호감도의 크기나 물건의 수다(쓰지 않는 종류는 비어 있다)."""

    model_config = ConfigDict(extra='ignore', frozen=True)

    kind: EffectKind
    target: str
    amount: int | None = None


def frozen(values: Mapping[str, int]) -> MappingProxyType[str, int]:
    """바꿀 수 없는 사전으로."""
    return MappingProxyType(dict(values))


def clamp_affection(value: int) -> int:
    """호감도를 범위 안으로 자른다."""
    return max(AFFECTION_MIN, min(AFFECTION_MAX, value))


def start_affection(world: 'World', cast_id: str) -> int:
    """판에 적힌 그 인물의 시작 호감도. 인물이 없으면 0."""
    member = world.member(cast_id)
    return member.affection.start if member is not None else AFFECTION_MIN


def change_affection(effect: Effect, state: 'StoryState', world: 'World') -> 'StoryState':
    """그 인물의 호감도를 amount 만큼 바꾼다. 상태에 없으면 판의 시작 값에서 바꾼다."""
    now = state.affection.get(effect.target, start_affection(world, effect.target))
    changed = {**state.affection, effect.target: clamp_affection(now + (effect.amount or 0))}
    return replace(state, affection=frozen(changed))


def give_item(effect: Effect, state: 'StoryState', world: 'World') -> 'StoryState':
    """사용자에게 그 물건을 amount 개 준다."""
    held = {**state.items, effect.target: state.items.get(effect.target, 0) + (effect.amount or 0)}
    return replace(state, items=frozen(held))


def take_item(effect: Effect, state: 'StoryState', world: 'World') -> 'StoryState':
    """사용자에게서 그 물건을 amount 개 가져간다. 가진 만큼까지다. 다 가져가면 소지품에서 뺀다."""
    left = state.items.get(effect.target, 0) - (effect.amount or 0)
    held = {item: count for item, count in state.items.items() if item != effect.target}
    if left > 0:
        held[effect.target] = left
    return replace(state, items=frozen(held))


def start_accompanying(effect: Effect, state: 'StoryState', world: 'World') -> 'StoryState':
    """그 인물과 동행을 시작한다. 동행의 차례는 시작한 차례다."""
    if effect.target in state.companions:
        return state
    return replace(state, companions=(*state.companions, effect.target))


def end_accompanying(effect: Effect, state: 'StoryState', world: 'World') -> 'StoryState':
    """그 인물과 동행을 끝낸다."""
    return replace(state, companions=tuple(cast_id for cast_id in state.companions if cast_id != effect.target))


def move_user(effect: Effect, state: 'StoryState', world: 'World') -> 'StoryState':
    """사용자(와 동행)를 그 장소로 옮긴다. 시간은 흐르지 않는다."""
    return replace(state, place=effect.target)


# 효과의 종류마다 반영하는 법
APPLIERS: dict[EffectKind, Callable[[Effect, 'StoryState', 'World'], 'StoryState']] = {
    EffectKind.AFFECTION: change_affection,
    EffectKind.GIVE_ITEM: give_item,
    EffectKind.TAKE_ITEM: take_item,
    EffectKind.ACCOMPANY_START: start_accompanying,
    EffectKind.ACCOMPANY_END: end_accompanying,
    EffectKind.MOVE_TO: move_user,
}


def apply_effect(effect: Effect, state: 'StoryState', world: 'World') -> 'StoryState':
    """효과 하나를 반영한 상태."""
    return APPLIERS[effect.kind](effect, state, world)


def apply_effects(effects: Iterable[Effect], state: 'StoryState', world: 'World') -> 'StoryState':
    """효과 목록을 적힌 차례대로 반영한 상태."""
    for effect in effects:
        state = apply_effect(effect, state, world)
    return state
