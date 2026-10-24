# story-server/app/engine/state.py

"""
엔진이 보는 지금의 상태(docs/architecture/story.md 의 "세션과 기록"). 바꾸지 않는 값이다.

상태는 말(메시지)마다 붙어 저장된다. 그 표와 읽고 쓰는 길은 말을 만드는 조각에서 더한다.
여기서는 모양과, 판으로 처음의 상태를 만드는 것만 둔다.
"""

from dataclasses import dataclass, field
from types import MappingProxyType

from app.engine.world import World

# 처음의 날짜. 1일째부터 센다
FIRST_DAY = 1


@dataclass(frozen=True)
class StoryState:
    """
    한 시점의 상태.

    day 와 slot 은 날짜와 시간대, place 는 사용자가 있는 장소다. items 는 소지품(물건 → 개수)이다.
    affection 은 인물마다의 호감도(인물 → 0~100), gifts 는 건넨 적이 있는 (인물, 물건)이다.
    seen 은 열린 적이 있는 이벤트, companions 는 동행 중인 인물(동행을 시작한 차례)이다.
    """

    day: int
    slot: str
    place: str
    items: MappingProxyType[str, int] = field(default_factory=lambda: MappingProxyType({}))
    affection: MappingProxyType[str, int] = field(default_factory=lambda: MappingProxyType({}))
    gifts: frozenset[tuple[str, str]] = frozenset()
    seen: frozenset[str] = frozenset()
    companions: tuple[str, ...] = ()


def start_items(world: World) -> dict[str, int]:
    """처음의 소지품. 같은 물건을 두 줄에 적었으면 더한다."""
    held: dict[str, int] = {}
    for entry in world.start_items:
        held[entry.item] = held.get(entry.item, 0) + entry.count
    return held


def start_state(world: World) -> StoryState:
    """판으로 만든 처음의 상태. 1일째, 처음의 시간대와 장소, 처음의 소지품, 인물마다의 시작 호감도다."""
    return StoryState(
        day=FIRST_DAY,
        slot=world.start_slot,
        place=world.start_place,
        items=MappingProxyType(start_items(world)),
        affection=MappingProxyType({member.id: member.affection.start for member in world.cast}),
    )
