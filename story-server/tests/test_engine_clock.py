# story-server/tests/test_engine_clock.py

"""
시각의 셈(app/engine/clock.py)을 검증한다. DB 를 쓰지 않는다. 시간대는 아침(7시), 낮(12시), 밤(19시)이다.

보는 것.
  - 며칠째는 자정에 바뀐다
  - 시간대는 시작 시각부터 다음 시간대 전까지다. 첫 시간대 전(새벽)은 마지막 시간대(밤)가 이어진다
  - 시작 시각은 1일째 처음의 시간대가 시작하는 때다(첫 시간대가 아니어도)
  - 다음 시간대의 시작: 오늘 남은 것이 없으면 다음 날의 첫 시간대
  - 하루를 마치고 닿는 시각: 다음 날의 첫 시간대. 자정을 넘겨 첫 시간대가 오지 않았으면 그날의 첫 시간대
  - 기한: N일이면 N+1일째부터 지났다. 기한이 없으면 지나지 않는다
"""

import pytest

from app.engine.clock import (
    day_of,
    deadline_passed,
    first_slot_after_rest,
    next_slot_start,
    slot_of,
    start_minutes,
)
from tests.engine_worlds import clock, world

WORLD = world()


@pytest.mark.parametrize(
    ('minutes', 'day'),
    [(clock(1, 0), 1), (clock(1, 23, 59), 1), (clock(2, 0), 2), (clock(30, 12), 30)],
)
def test_the_day_changes_at_midnight(minutes: int, day: int):
    assert day_of(minutes) == day


@pytest.mark.parametrize(
    ('minutes', 'slot'),
    [
        (clock(1, 7), 'morning'),
        (clock(1, 11, 59), 'morning'),
        (clock(1, 12), 'day'),
        (clock(1, 19), 'night'),
        (clock(1, 23, 59), 'night'),
        (clock(2, 2), 'night'),
        (clock(2, 6, 59), 'night'),
        (clock(2, 7), 'morning'),
    ],
)
def test_the_slot_runs_until_the_next_one(minutes: int, slot: str):
    assert slot_of(WORLD, minutes) == slot


def test_the_start_is_the_start_slot_on_day_one():
    assert start_minutes(WORLD) == clock(1, 7)
    assert start_minutes(world(start_slot='night')) == clock(1, 19)


@pytest.mark.parametrize(
    ('now', 'expected'),
    [
        (clock(1, 7), clock(1, 12)),
        (clock(1, 9, 30), clock(1, 12)),
        (clock(1, 12), clock(1, 19)),
        (clock(1, 20), clock(2, 7)),
        (clock(2, 2), clock(2, 7)),
    ],
)
def test_the_next_slot_start(now: int, expected: int):
    assert next_slot_start(WORLD, now) == expected


@pytest.mark.parametrize(
    ('now', 'expected'),
    [
        (clock(1, 7), clock(2, 7)),
        (clock(1, 20), clock(2, 7)),
        (clock(2, 2), clock(2, 7)),
        (clock(2, 7), clock(3, 7)),
    ],
)
def test_resting_reaches_the_first_slot_of_the_next_day(now: int, expected: int):
    assert first_slot_after_rest(WORLD, now) == expected


def test_a_single_slot_world_moves_a_day_at_a_time():
    single = world(slots=[{'id': 'all', 'name': '하루', 'start_hour': 0}], start_slot='all')

    assert next_slot_start(single, clock(1, 15)) == clock(2, 0)
    assert first_slot_after_rest(single, clock(1, 15)) == clock(2, 0)
    assert slot_of(single, clock(3, 4)) == 'all'


@pytest.mark.parametrize(
    ('deadline', 'minutes', 'passed'),
    [(30, clock(30, 23, 59), False), (30, clock(31, 0), True), (None, clock(999, 0), False)],
)
def test_the_deadline_passes_on_the_next_day(deadline: int | None, minutes: int, passed: bool):
    assert deadline_passed(world(deadline_days=deadline), minutes) is passed
