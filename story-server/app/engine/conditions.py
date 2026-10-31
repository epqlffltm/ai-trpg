# story-server/app/engine/conditions.py

"""
조건을 맞춘다(docs/architecture/story.md 의 "조건"). 일정의 줄, 이벤트가 열리는 조건, 고백, 엔딩이 모두 이것을 쓴다.

엔진이 이미 아는 사실(상태와 판)만 본다. 대화의 내용은 보지 않는다.
조건 목록이 비면 늘 맞는다(조건 없는 일정의 줄, 조건 없는 엔딩).

TRPG 의 퀘스트 조건(trpg-server 의 app/rounds/quest_goals.py)과 모양은 같지만 코드는 나누지 않는다.
종류가 겹치지 않고(story 는 호감도, 날짜, 동행, TRPG 는 몬스터, 퀘스트 잇기), 빈 목록의 뜻도 다르다
(TRPG 는 조건이 없으면 이루지 않는다). 함께 쓸 수 있는 것은 "모두/하나라도"를 고르는 한 줄뿐이다.
"""

from collections.abc import Callable

from app.engine.clock import day_of, slot_of
from app.engine.state import StoryState
from app.engine.world import Condition, ConditionKind, Conditions, Match, World


def stage_floor(world: World, cast_id: str | None, stage_name: str | None) -> int | None:
    """그 인물의 그 단계가 시작하는 호감도. 인물이나 단계가 없으면 None 이다."""
    member = world.member(cast_id or '')
    if member is None:
        return None
    return next((stage.at for stage in member.affection.stages if stage.name == stage_name), None)


def affection_of(state: StoryState, world: World, cast_id: str | None) -> int:
    """그 인물의 지금 호감도. 상태에 없으면 판의 시작 값이다."""
    member = world.member(cast_id or '')
    start = member.affection.start if member is not None else 0
    return state.affection.get(cast_id or '', start)


def affection_at_least(condition: Condition, state: StoryState, world: World) -> bool:
    """그 인물의 호감도가 그 단계 이상인가. 없는 단계면 아니다."""
    floor = stage_floor(world, condition.target, condition.value)
    return floor is not None and affection_of(state, world, condition.target) >= floor


def affection_below(condition: Condition, state: StoryState, world: World) -> bool:
    """그 인물의 호감도가 그 단계보다 아래인가. 없는 단계면 아니다."""
    floor = stage_floor(world, condition.target, condition.value)
    return floor is not None and affection_of(state, world, condition.target) < floor


# 조건의 종류마다 맞추는 법. 판은 게시할 때 검사했으므로 종류마다 쓰는 칸이 채워져 있다
CHECKS: dict[ConditionKind, Callable[[Condition, StoryState, World], bool]] = {
    ConditionKind.REACH_PLACE: lambda condition, state, world: state.place == condition.target,
    ConditionKind.HOLD_ITEM: lambda condition, state, world: (
        state.items.get(condition.target or '', 0) >= condition.count
    ),
    ConditionKind.GAVE_ITEM: lambda condition, state, world: (condition.target, condition.value) in state.gifts,
    ConditionKind.AFFECTION_AT_LEAST: affection_at_least,
    ConditionKind.AFFECTION_BELOW: affection_below,
    ConditionKind.DAY_AT_LEAST: lambda condition, state, world: day_of(state.minutes) >= condition.count,
    ConditionKind.DAY_AT_MOST: lambda condition, state, world: day_of(state.minutes) <= condition.count,
    ConditionKind.SLOT_IS: lambda condition, state, world: slot_of(world, state.minutes) == condition.target,
    ConditionKind.ACCOMPANIED: lambda condition, state, world: condition.target in state.companions,
    ConditionKind.EVENT_SEEN: lambda condition, state, world: condition.target in state.seen,
    ConditionKind.ENDING_SEEN: lambda condition, state, world: condition.target in state.cleared,
}


def is_met(condition: Condition, state: StoryState, world: World) -> bool:
    """조건 하나가 지금 맞는가."""
    return CHECKS[condition.kind](condition, state, world)


def match_conditions(conditions: Conditions, state: StoryState, world: World) -> bool:
    """조건 목록이 맞는가. 비면 맞는다. 모두(all) 또는 하나라도(any)는 목록이 정한다."""
    if not conditions.items:
        return True
    met = (is_met(condition, state, world) for condition in conditions.items)
    return all(met) if conditions.match == Match.ALL else any(met)
