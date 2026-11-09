# story-server/app/engine/achievements.py

"""
업적을 준다(docs/architecture/achievements.md 의 "story"). 판과 상태만 보는 순수한 함수다. DB 를 모른다.

업적은 제작자가 작품에 단 것이다(스팀의 업적과 같다). 인증 서버의 활동 배지와는 다른 것이다.
  - 행동 뒤의 상태로 본다. 엔진이 이벤트, 장, 엔딩을 다 본 뒤의 상태다. 대화의 내용과 모델의 글은 보지 않는다
  - 조건의 모양과 종류는 이벤트의 조건과 같다(app/engine/conditions.py). 다른 것은 둘이다
    · 조건이 비면 주지 않는다. 이벤트는 빈 조건이 늘 맞지만, 업적이 늘 맞으면 첫 행동에 그냥 받는다
      (asset 이 게시할 때도 막는다)
    · 엔딩을 봤다(ending_seen)는 이 가지에서 방금 닿은 엔딩도 본 것으로 친다.
      회차 혜택은 세션을 시작할 때의 기록만 보지만, "그 엔딩을 봤다"는 업적은 엔딩에 닿은 그 행동에 받아야 한다
  - 계정마다 한 번이다. 이미 받은 것(owned)은 다시 주지 않는다. 받은 차례는 판의 차례다
"""

from dataclasses import replace

from app.engine.conditions import match_conditions
from app.engine.state import StoryState
from app.engine.world import Achievement, World


def with_reached_ending(state: StoryState) -> StoryState:
    """이 가지에서 닿은 엔딩을 본 엔딩에 더한 상태. 닿은 엔딩이 없으면 그대로다."""
    if state.ending is None:
        return state
    return replace(state, cleared=state.cleared | {state.ending})


def is_earned(achievement: Achievement, state: StoryState, world: World) -> bool:
    """그 업적의 조건이 지금 맞는가. 조건이 없으면 아니다."""
    return bool(achievement.when.items) and match_conditions(achievement.when, state, world)


def newly_earned(world: World, state: StoryState, owned: frozenset[str]) -> tuple[Achievement, ...]:
    """아직 받지 않은 업적 가운데 지금 조건이 맞는 것들. 판의 차례다."""
    seen = with_reached_ending(state)
    return tuple(
        achievement
        for achievement in world.achievements
        if achievement.id not in owned and is_earned(achievement, seen, world)
    )
