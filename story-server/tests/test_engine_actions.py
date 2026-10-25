# story-server/tests/test_engine_actions.py

"""
시각을 흘리는 행동(app/engine/actions.py)을 검증한다. DB 를 쓰지 않는다. 시간대는 아침(7시), 낮(12시), 밤(19시)이다.

보는 것.
  - 이동: 길로 바로 이어진 장소로만 간다(양쪽으로). 길의 시간만큼 흐르고, 시간대의 경계를 넘으면 시간대가 바뀐다.
    지금 있는 곳이나 길이 없는 곳이면 CannotMove 다. 동행은 따라온다(장면의 인물에 남는다)
  - 시간 보내기는 다음 시간대의 시작, 마지막 시간대에서는 하루 마치기와 같은 곳
  - 하루 마치기는 다음 날의 첫 시간대
  - 행동은 상태의 다른 칸을 바꾸지 않는다
"""

from dataclasses import replace

import pytest

from app.engine.actions import CannotMove, end_day, move_to, pass_time, path_minutes
from app.engine.clock import slot_of
from app.engine.scene import scene_cast
from app.engine.state import start_state
from tests.engine_worlds import clock, member, world

PATHS = [
    {'a': 'home', 'b': 'school', 'minutes': 20},
    {'a': 'school', 'b': 'library', 'minutes': 300},
    {'a': 'home', 'b': 'yard', 'minutes': 0},
]
WORLD = world([member('mina', 'library'), member('yuna', 'home')], paths=PATHS)
START = start_state(WORLD)


def test_a_path_works_both_ways():
    assert path_minutes(WORLD, 'home', 'school') == 20
    assert path_minutes(WORLD, 'school', 'home') == 20
    assert path_minutes(WORLD, 'home', 'library') is None


def test_moving_takes_the_paths_time():
    moved = move_to(WORLD, START, 'school')

    assert (moved.place, moved.minutes) == ('school', clock(1, 7, 20))
    assert replace(moved, place=START.place, minutes=START.minutes) == START


def test_a_long_move_crosses_into_the_next_slot():
    moved = move_to(WORLD, replace(START, place='school', minutes=clock(1, 10)), 'library')

    assert (moved.minutes, slot_of(WORLD, moved.minutes)) == (clock(1, 15), 'day')


def test_a_zero_minute_path_moves_without_time():
    moved = move_to(WORLD, START, 'yard')

    assert (moved.place, moved.minutes) == ('yard', START.minutes)


@pytest.mark.parametrize('place', ['home', 'library', 'nowhere'])
def test_one_cannot_move_here_or_without_a_path(place: str):
    with pytest.raises(CannotMove):
        move_to(WORLD, START, place)


def test_a_companion_follows():
    with_yuna = replace(START, companions=('yuna',))

    moved = move_to(WORLD, with_yuna, 'school')

    assert scene_cast(WORLD, moved) == ['yuna']
    assert scene_cast(WORLD, move_to(WORLD, START, 'school')) == []


@pytest.mark.parametrize(
    ('now', 'expected'),
    [(clock(1, 7), clock(1, 12)), (clock(1, 15), clock(1, 19)), (clock(1, 19, 30), clock(2, 7))],
)
def test_passing_time_goes_to_the_next_slot(now: int, expected: int):
    assert pass_time(WORLD, replace(START, minutes=now)).minutes == expected


def test_passing_time_in_the_last_slot_is_ending_the_day():
    night = replace(START, minutes=clock(1, 21))

    assert pass_time(WORLD, night) == end_day(WORLD, night)


@pytest.mark.parametrize(
    ('now', 'expected'),
    [(clock(1, 7), clock(2, 7)), (clock(1, 13), clock(2, 7)), (clock(2, 1), clock(2, 7))],
)
def test_ending_the_day_goes_to_the_next_morning(now: int, expected: int):
    rested = end_day(WORLD, replace(START, minutes=now))

    assert rested.minutes == expected
    assert rested.place == START.place
