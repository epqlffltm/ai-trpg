# story-server/app/engine/scene.py

"""
인물이 어디에 있는가와 장면의 인물(docs/architecture/story.md 의 "인물과 장면"). 엔진이 정한다.

인물의 자리는 높은 것부터 본다.
  1. 동행 중이면 사용자와 같은 곳
  2. 일정에 지금의 시간대와 맞는 줄이 있고 그 줄의 조건이 맞으면 그 장소. 위의 줄부터 본다
  3. 아니면 기본 장소. 비어 있으면 어디에도 없다(이벤트로만 나온다)

장면의 인물은 사용자가 있는 장소에 있는 인물과, 열린 이벤트가 부른 인물이다. 상한(SCENE_MAX_CAST)을 넘으면
동행, 이벤트, 일정, 기본 장소의 차례로, 같은 차례에서는 판에 적은 인물의 차례로 고른다.
보이기(보임, 실루엣, 숨김)는 화면에 어떻게 보일지의 일이라 여기서 거르지 않는다.
"""

import enum
from dataclasses import dataclass

from app.engine.clock import slot_of
from app.engine.conditions import match_conditions
from app.engine.state import StoryState
from app.engine.world import CastMember, World

# 장면에 한 번에 나오는 인물의 상한. asset 서버의 장면 지시(SCENE_MAX_CAST)와 같다
SCENE_MAX_CAST = 4


class Presence(enum.IntEnum):
    """인물이 왜 그 자리에 있는가. 값이 작을수록 장면의 인물을 고를 때 앞선다."""

    COMPANION = 0
    EVENT = 1
    SCHEDULE = 2
    HOME = 3


@dataclass(frozen=True)
class Whereabouts:
    """인물이 있는 장소와 그 까닭. 어디에도 없으면 place 가 None 이다."""

    place: str | None
    presence: Presence | None


NOWHERE = Whereabouts(None, None)


def scheduled_place(member: CastMember, state: StoryState, world: World) -> str | None:
    """일정에서 지금의 시간대와 조건에 맞는 첫 줄의 장소. 맞는 줄이 없으면 None."""
    slot = slot_of(world, state.minutes)
    for line in member.schedule:
        if line.slot == slot and match_conditions(line.when, state, world):
            return line.place
    return None


def place_of_character(member: CastMember, state: StoryState, world: World) -> Whereabouts:
    """인물이 지금 있는 장소와 그 까닭. 동행, 일정, 기본 장소의 차례로 본다."""
    if member.id in state.companions:
        return Whereabouts(state.place, Presence.COMPANION)
    scheduled = scheduled_place(member, state, world)
    if scheduled is not None:
        return Whereabouts(scheduled, Presence.SCHEDULE)
    if member.home is not None:
        return Whereabouts(member.home, Presence.HOME)
    return NOWHERE


def presence_here(member: CastMember, state: StoryState, world: World, called: frozenset[str]) -> Presence | None:
    """
    인물이 장면에 들어오는 까닭. 들어오지 않으면 None.

    동행이 가장 앞선다. 그다음 이벤트가 부른 것, 그다음 사용자와 같은 장소에 있는 것(일정, 기본 장소)이다.
    """
    whereabouts = place_of_character(member, state, world)
    if whereabouts.presence == Presence.COMPANION:
        return Presence.COMPANION
    if member.id in called:
        return Presence.EVENT
    if whereabouts.place == state.place:
        return whereabouts.presence
    return None


def scene_cast(world: World, state: StoryState, called: tuple[str, ...] = ()) -> list[str]:
    """
    장면의 인물(인물의 id). called 는 열린 이벤트가 부른 인물이다.

    상한을 넘으면 까닭의 차례(Presence), 같은 까닭에서는 판에 적은 인물의 차례로 고른다.
    돌려주는 목록도 그 차례다.
    """
    wanted = frozenset(called)
    present = []
    for order, member in enumerate(world.cast):
        presence = presence_here(member, state, world, wanted)
        if presence is not None:
            present.append((presence, order, member.id))
    return [cast_id for _, _, cast_id in sorted(present)[:SCENE_MAX_CAST]]
