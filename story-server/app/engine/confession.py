# story-server/app/engine/confession.py

"""
고백(docs/architecture/story.md 의 "고백과 엔딩"). 판과 상태만 보는 순수 함수다.

장면에 있는 인물 하나를 골라 하는 행동이다.
  1. 그 인물의 고백의 성공 조건을 본다. 호감도가 정한 단계 이상이고 조건 목록이 맞으면 성공이다
  2. 성공이면 "그 인물에게 고백 성공"의 엔딩을 판정한다
  3. 실패면 그 인물에 정한 대로 한다
     - 계속(기본): 호감도를 정한 만큼 내리고(0 아래로는 가지 않는다), 정한 날 동안 다시 고백하지 못한다
     - 끝: "그 인물에게 고백 실패"의 엔딩을 판정한다

받지 않는 고백(ConfessionRefused): 이미 엔딩을 봤다, 장면에 없는 인물이다, 고백할 수 없는 인물이다,
다시 고백할 시각이 아직이다.
성공과 실패는 엔진만 정한다. 모델은 그 결과에 맞는 반응만 쓴다.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType

from app.engine.clock import MINUTES_PER_DAY
from app.engine.conditions import affection_of, match_conditions, stage_floor
from app.engine.effects import clamp_affection
from app.engine.endings import is_over, pick_ending, reach_ending
from app.engine.state import StoryState
from app.engine.world import CastMember, Confession, ConfessionFailure, Ending, EndingTrigger, World


class Refusal(enum.StrEnum):
    """고백을 받지 않는 까닭. 화면이 안내를 고른다."""

    OVER = 'over'
    NOT_IN_SCENE = 'not_in_scene'
    NOT_CONFESSABLE = 'not_confessable'
    COOLING_DOWN = 'cooling_down'


class ConfessionRefused(Exception):
    """그 고백을 받지 않는다. reason 이 까닭이다."""

    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Outcome:
    """고백의 결과. 고백 뒤의 상태, 성공했는가, 그 고백으로 본 엔딩(없으면 None)."""

    state: StoryState
    succeeded: bool
    ending: Ending | None


def confession_of(world: World, state: StoryState, cast_id: str, scene: Sequence[str]) -> tuple[CastMember, Confession]:
    """고백을 받을 인물과 그 고백의 정의. 받지 않는 고백이면 ConfessionRefused."""
    if is_over(state):
        raise ConfessionRefused(Refusal.OVER)
    if cast_id not in scene:
        raise ConfessionRefused(Refusal.NOT_IN_SCENE)
    member = world.member(cast_id)
    if member is None or member.confession is None:
        raise ConfessionRefused(Refusal.NOT_CONFESSABLE)
    if state.minutes < state.cooldowns.get(cast_id, 0):
        raise ConfessionRefused(Refusal.COOLING_DOWN)
    return member, member.confession


def is_accepted(world: World, state: StoryState, member: CastMember, confession: Confession) -> bool:
    """고백이 성공하는가. 호감도가 그 단계 이상이고 조건 목록이 맞아야 한다. 없는 단계면 실패다."""
    floor = stage_floor(world, member.id, confession.stage)
    if floor is None or affection_of(state, world, member.id) < floor:
        return False
    return match_conditions(confession.when, state, world)


def cool_down(world: World, state: StoryState, member: CastMember, confession: Confession) -> StoryState:
    """계속하는 실패. 호감도를 내리고 정한 날 동안 다시 고백하지 못하게 한다."""
    dropped = clamp_affection(affection_of(state, world, member.id) - confession.fail_drop)
    until = state.minutes + confession.cooldown_days * MINUTES_PER_DAY
    return replace(
        state,
        affection=MappingProxyType({**state.affection, member.id: dropped}),
        cooldowns=MappingProxyType({**state.cooldowns, member.id: until}),
    )


def end_with(world: World, state: StoryState, kind: EndingTrigger, cast_id: str) -> tuple[StoryState, Ending | None]:
    """그 시작의 엔딩을 판정한 상태와 그 엔딩. 맞는 엔딩이 없으면 상태 그대로와 None."""
    ending = pick_ending(world, state, kind, cast_id)
    if ending is None:
        return state, None
    return reach_ending(state, ending), ending


def confess(world: World, state: StoryState, cast_id: str, scene: Sequence[str]) -> Outcome:
    """
    그 인물에게 고백한 결과. scene 은 지금 장면의 인물이다(app/engine/scene.py 의 scene_cast).

    받지 않는 고백이면 ConfessionRefused.
    """
    member, confession = confession_of(world, state, cast_id, scene)
    if is_accepted(world, state, member, confession):
        ended, ending = end_with(world, state, EndingTrigger.CONFESS_SUCCESS, cast_id)
        return Outcome(ended, True, ending)
    if confession.on_fail == ConfessionFailure.END:
        ended, ending = end_with(world, state, EndingTrigger.CONFESS_FAIL, cast_id)
        return Outcome(ended, False, ending)
    return Outcome(cool_down(world, state, member, confession), False, None)
