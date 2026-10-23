# chat-server/tests/test_world_clock.py

"""
대화 안의 시각, 시간 보내기, 배경 고르기(app/world/clock.py, waiting.py, backgrounds.py)를 검증한다(#668).
DB 를 쓰지 않는다.

보는 것.
  - 시간대의 경계는 TRPG 와 같다(새벽 4시, 아침 7시, 낮 11시, 저녁 17시, 밤 21시. 4시 전은 밤)
  - 시각은 시작 시각에 흐른 시간을 더한 것이고, 하루를 넘으면 며칠째가 오른다
  - 시간 보내기는 다음 시간대의 시작까지 흐른다. 밤이면 다음 날 새벽이다. 경계에 있으면 그다음 경계까지다
  - 배경은 그 시간대의 것, 없으면 장소의 기본 배경, 그것도 없거나 장소가 없으면 없다
"""

import uuid

import pytest

from app.assets.schemas import CharacterDocument, PlaceDocument
from app.world.actions import perform
from app.world.backgrounds import background_of
from app.world.clock import (
    TimeOfDay,
    clock_minutes,
    read_time,
    time_of_day,
    time_words,
    until_next_time_of_day,
)
from app.world.schemas import WaitAction
from app.world.state import WorldState
from app.world.waiting import apply_wait, wait_text
from tests.assets import make_character

BASE = uuid.UUID(int=1)
NIGHT_PICTURE = uuid.UUID(int=2)
LIBRARY = PlaceDocument(
    id='library', name='도서관', description='', image_id=BASE, backgrounds={'night': NIGHT_PICTURE}
)
BARE = PlaceDocument(id='roof', name='옥상', description='', image_id=None)
DOCUMENT: CharacterDocument = make_character(world={'places': [LIBRARY, BARE], 'start_place': 'library'}).document
NOWHERE = WorldState(place=None, minutes=0, inventory=(), visited=())


def at(hour: int, minute: int = 0) -> int:
    """1일째 hour 시 minute 분."""
    return hour * 60 + minute


# --- 시간대 ---


@pytest.mark.parametrize(
    ('hour', 'part'),
    [
        (0, TimeOfDay.NIGHT),
        (3, TimeOfDay.NIGHT),
        (4, TimeOfDay.DAWN),
        (6, TimeOfDay.DAWN),
        (7, TimeOfDay.MORNING),
        (10, TimeOfDay.MORNING),
        (11, TimeOfDay.DAY),
        (16, TimeOfDay.DAY),
        (17, TimeOfDay.EVENING),
        (20, TimeOfDay.EVENING),
        (21, TimeOfDay.NIGHT),
        (23, TimeOfDay.NIGHT),
    ],
)
def test_the_times_of_day_have_the_same_borders_as_trpg(hour: int, part: TimeOfDay):
    assert time_of_day(hour) == part


def test_the_clock_is_the_start_hour_plus_the_elapsed_minutes():
    assert clock_minutes(21, 0) == at(21)
    assert clock_minutes(21, 75) == at(22, 15)


def test_reading_the_time_rolls_over_to_the_next_day():
    late = read_time(at(23, 59))
    next_day = read_time(at(23, 59) + 1)

    assert (late.day, late.hour, late.minute, late.time_of_day) == (1, 23, 59, TimeOfDay.NIGHT)
    assert (next_day.day, next_day.hour, next_day.minute, next_day.time_of_day) == (2, 0, 0, TimeOfDay.NIGHT)
    assert time_words(read_time(clock_minutes(17, 24 * 60 + 90))) == '2일째 저녁 18:30'


# --- 시간 보내기 ---


@pytest.mark.parametrize(
    ('now', 'left'),
    [
        (at(12), at(5)),  # 낮 → 17시 저녁
        (at(16, 59), 1),
        (at(17), at(4)),  # 경계에 있으면 그다음 경계(21시)까지
        (at(21), at(7)),  # 밤 → 다음 날 4시
        (at(23, 59), at(4, 1)),
        (at(2), at(2)),  # 자정이 지난 밤 → 그날 4시
        (at(3, 59), 1),
        (at(4), at(3)),
        (24 * 60 + at(10), at(1)),  # 2일째도 같다
    ],
)
def test_waiting_runs_to_the_start_of_the_next_time_of_day(now: int, left: int):
    assert until_next_time_of_day(now) == left


def test_waiting_moves_the_state_and_tells_the_new_time_of_day():
    waited = apply_wait(NOWHERE, 21)

    assert waited.minutes == at(7)
    assert read_time(clock_minutes(21, waited.minutes)).day == 2
    assert wait_text(waited, 21) == '시간을 보냈다. 새벽이 되었다.'


def test_waiting_keeps_everything_else():
    state = WorldState(place='library', minutes=30, inventory=(), visited=('library',), affection=40, fired=('a',))

    waited = apply_wait(state, 12)

    assert (waited.place, waited.visited, waited.affection, waited.fired) == ('library', ('library',), 40, ('a',))
    assert waited.minutes == 30 + at(4, 30)


def test_waiting_is_an_action_without_a_map():
    performed = perform(DOCUMENT, NOWHERE, WaitAction(kind='wait'), 12)

    assert (performed.state.minutes, performed.text) == (at(5), '시간을 보냈다. 저녁이 되었다.')


# --- 배경 ---


def test_the_background_of_the_time_of_day_comes_first():
    assert background_of(DOCUMENT, 'library', TimeOfDay.NIGHT) == NIGHT_PICTURE


def test_without_one_for_the_time_of_day_the_base_background_is_used():
    assert background_of(DOCUMENT, 'library', TimeOfDay.DAWN) == BASE


def test_no_place_or_no_picture_is_no_background():
    assert background_of(DOCUMENT, 'roof', TimeOfDay.NIGHT) is None
    assert background_of(DOCUMENT, None, TimeOfDay.NIGHT) is None
    assert background_of(DOCUMENT, 'gone', TimeOfDay.NIGHT) is None
