# story-server/app/engine/endings.py

"""
엔딩의 판정(docs/architecture/story.md 의 "고백과 엔딩"). 판과 상태만 보는 순수 함수다.

시작(고백 성공·실패, 기한, 이벤트)이 일어나면 그 시작의 엔딩을 판에 적은 차례로 맞춰 보고 조건이 맞는 첫 엔딩을 고른다.
asset 서버는 쓰일 수 있는 시작마다 조건이 빈 엔딩이 하나는 있어야 게시한다(ending_missing).
그래서 판정은 늘 무언가를 고른다.
그래도 고를 것이 없으면(앞 형식의 판) None 이고, 세션은 끝나지 않는다.

엔딩을 보면 상태의 ending 에 적는다. 그 뒤로는 엔딩과 기한이 다시 일어나지 않고 고백을 받지 않는다
(엔딩 뒤가 끝이든 후일담이든 같다. 끝이면 말과 행동을 받지 않는 것은 세션 쪽의 일이다).
계정의 엔딩 기록과 엔딩의 장면(모델이 쓰는 글)은 이 모듈 밖의 일이다.
"""

from dataclasses import replace

from app.engine.clock import deadline_passed
from app.engine.conditions import match_conditions
from app.engine.state import StoryState
from app.engine.world import Ending, EndingTrigger, World


def is_over(state: StoryState) -> bool:
    """이 가지에서 이미 엔딩을 봤는가."""
    return state.ending is not None


def pick_ending(world: World, state: StoryState, kind: EndingTrigger, target: str | None = None) -> Ending | None:
    """그 시작의 엔딩 가운데 조건이 맞는 첫 엔딩. 이미 엔딩을 봤거나 맞는 것이 없으면 None."""
    if is_over(state):
        return None
    for ending in world.endings:
        if (
            ending.trigger.kind == kind
            and ending.trigger.target == target
            and match_conditions(ending.when, state, world)
        ):
            return ending
    return None


def reach_ending(state: StoryState, ending: Ending) -> StoryState:
    """그 엔딩을 본 상태."""
    return replace(state, ending=ending.id, choosing=None)


def deadline_ending(world: World, state: StoryState) -> Ending | None:
    """기한이 지났으면 기한의 엔딩. 기한이 없거나 지나지 않았거나 이미 엔딩을 봤으면 None."""
    if not deadline_passed(world, state.minutes):
        return None
    return pick_ending(world, state, EndingTrigger.DEADLINE)


def event_ending(world: World, state: StoryState, event_id: str) -> Ending | None:
    """그 이벤트가 열려 시작되는 엔딩. 없으면 None."""
    return pick_ending(world, state, EndingTrigger.EVENT, event_id)
