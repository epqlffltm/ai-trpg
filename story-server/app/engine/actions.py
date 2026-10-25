# story-server/app/engine/actions.py

"""
시각을 흘리는 행동(docs/architecture/story.md 의 "시각"). 판과 상태를 받아 행동 뒤의 상태를 돌려주는 순수 함수다.

  - 이동(move_to): 지금 있는 장소와 길로 바로 이어진 장소로만 간다(chat 의 app/world/moves.py 와 같다).
    길에 적은 시간만큼 시각이 흐른다. 동행 중인 인물은 따라온다. 인물의 자리는 상태의 장소로 계산하므로
    따로 옮기지 않는다(app/engine/scene.py)
  - 시간 보내기(pass_time): 다음 시간대의 시작으로
  - 하루 마치기(end_day): 다음 날의 첫 시간대로. 자정을 넘겨 그날의 첫 시간대가 아직 오지 않았으면 그날의 첫 시간대로
마지막 시간대에서 시간 보내기를 하면 하루 마치기와 같은 곳에 닿는다.
모두 사용자의 행동이다. 시각은 대화의 길이로 흐르지 않는다. 행동 자체는 모델을 부르지 않는다.
"""

from dataclasses import replace

from app.engine.clock import first_slot_after_rest, next_slot_start
from app.engine.state import StoryState
from app.engine.world import World


class CannotMove(Exception):
    """그 장소로 갈 수 없다. 지금 있는 곳이거나, 길로 바로 이어지지 않았다."""


def path_minutes(world: World, start: str, end: str) -> int | None:
    """두 장소를 잇는 길에 걸리는 분. 길이 없으면 None. 길은 양쪽으로 다닌다."""
    for path in world.paths:
        if {path.a, path.b} == {start, end}:
            return path.minutes
    return None


def move_to(world: World, state: StoryState, place: str) -> StoryState:
    """그 장소로 옮긴 상태. 길의 시간만큼 시각이 흐른다. 갈 수 없으면 CannotMove."""
    if place == state.place:
        raise CannotMove
    minutes = path_minutes(world, state.place, place)
    if minutes is None:
        raise CannotMove
    return replace(state, place=place, minutes=state.minutes + minutes)


def pass_time(world: World, state: StoryState) -> StoryState:
    """시간 보내기. 다음 시간대의 시작으로 간다."""
    return replace(state, minutes=next_slot_start(world, state.minutes))


def end_day(world: World, state: StoryState) -> StoryState:
    """하루 마치기. 다음 날의 첫 시간대로 간다."""
    return replace(state, minutes=first_slot_after_rest(world, state.minutes))
