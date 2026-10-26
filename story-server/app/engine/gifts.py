# story-server/app/engine/gifts.py

"""
건네기(docs/architecture/story.md 의 "행동"). 판과 상태만 보는 순수 함수다.

장면에 있는 인물 하나에게 가진 물건 하나를 건네는 행동이다.
  1. 그 인물이 장면에 있고 그 물건을 하나 이상 가졌는지 본다. 아니면 GiftRefused
  2. 물건이 하나 줄고, 건넨 적이 있는 (인물, 물건)에 넣는다(조건 gave_item 이 본다)
  3. 그 인물의 선물 규칙 가운데 그 물건의 것들을 판의 차례대로 더해 호감도를 바꾼다.
     하나 더할 때마다 0~100 안으로 자른다
     (chat 의 app/world/affection.py 와 같다). once 인 규칙은 그 인물에게 그 물건을 처음 건넬 때만 든다.
     맞는 규칙이 없으면 호감도는 그대로다

once 를 규칙의 id 로 따로 적지 않는다. once 인 규칙은 그 물건을 건넬 때만 들므로
"그 규칙이 든 적이 있다"는 "그 인물에게 그 물건을 건넨 적이 있다"(상태의 gifts)와 같다.
엔딩을 본 뒤(후일담)에도 건넬 수 있다. 시각은 흐르지 않는다.
호감도가 얼마나 바뀌었는지는 엔진만 정한다. 모델은 그 결과에 맞는 반응만 쓴다.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass, replace

from app.engine.conditions import affection_of
from app.engine.effects import clamp_affection, frozen
from app.engine.state import StoryState
from app.engine.world import Gift, World


class GiftRefusal(enum.StrEnum):
    """건네기를 받지 않는 까닭. 화면이 안내를 고른다."""

    NOT_IN_SCENE = 'not_in_scene'
    NOT_HELD = 'not_held'


class GiftRefused(Exception):
    """그 건네기를 받지 않는다. reason 이 까닭이다."""

    def __init__(self, reason: GiftRefusal) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Given:
    """건넨 결과. 건넨 뒤의 상태와, 든 규칙들의 change 의 합(자르기 전. 맞는 규칙이 없으면 0)."""

    state: StoryState
    change: int


def require_giftable(state: StoryState, cast_id: str, item: str, scene: Sequence[str]) -> None:
    """장면에 없는 인물이거나 그 물건이 없으면 GiftRefused."""
    if cast_id not in scene:
        raise GiftRefused(GiftRefusal.NOT_IN_SCENE)
    if state.items.get(item, 0) < 1:
        raise GiftRefused(GiftRefusal.NOT_HELD)


def matching_gifts(world: World, cast_id: str, item: str, first: bool) -> tuple[Gift, ...]:
    """그 인물에게 그 물건을 건넬 때 드는 규칙들. first 가 아니면 once 인 규칙은 빠진다."""
    member = world.member(cast_id)
    if member is None:
        return ()
    return tuple(gift for gift in member.affection.gifts if gift.item == item and (first or not gift.once))


def handed_over(state: StoryState, cast_id: str, item: str) -> StoryState:
    """물건 하나를 내주고 건넨 적이 있는 (인물, 물건)에 넣은 상태. 다 내주면 소지품에서 뺀다."""
    left = state.items[item] - 1
    held = {key: count for key, count in state.items.items() if key != item}
    if left > 0:
        held[item] = left
    return replace(state, items=frozen(held), gifts=state.gifts | {(cast_id, item)})


def with_affection(world: World, state: StoryState, cast_id: str, gifts: Sequence[Gift]) -> StoryState:
    """그 인물의 호감도에 규칙들을 차례로 더한 상태. 하나 더할 때마다 0~100 안으로 자른다. 규칙이 없으면 그대로다."""
    if not gifts:
        return state
    value = affection_of(state, world, cast_id)
    for gift in gifts:
        value = clamp_affection(value + gift.change)
    return replace(state, affection=frozen({**state.affection, cast_id: value}))


def give(world: World, state: StoryState, cast_id: str, item: str, scene: Sequence[str]) -> Given:
    """장면(scene)에 있는 인물에게 물건 하나를 건넨다. 받지 않는 건네기면 GiftRefused."""
    require_giftable(state, cast_id, item, scene)
    first = (cast_id, item) not in state.gifts
    gifts = matching_gifts(world, cast_id, item, first)
    given = with_affection(world, handed_over(state, cast_id, item), cast_id, gifts)
    return Given(state=given, change=sum(gift.change for gift in gifts))
