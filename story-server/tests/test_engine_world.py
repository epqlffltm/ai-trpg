# story-server/tests/test_engine_world.py

"""
엔진이 판을 읽는 모양(app/engine/world.py)과 처음의 상태(app/engine/state.py)를 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 엔진이 쓰는 칸만 읽고 모르는 칸은 버린다. 인물과 이벤트는 판의 차례 그대로다
  - 형식 1 의 판(이벤트가 없다)도 읽는다. 쓰지 않는 칸을 비운 조건도 읽는다(count 는 1)
  - 처음의 상태: 1일째, 처음의 시간대와 장소, 처음의 소지품(같은 물건은 더한다), 인물마다의 시작 호감도
  - 상태는 바꿀 수 없다
"""

import dataclasses

import pytest

from app.engine.state import start_state
from app.engine.world import ConditionKind, Match, read_world
from tests.engine_worlds import condition, document, line, member, world


def test_only_the_engines_fields_are_read_in_order():
    read = world(
        [member('mina', 'cafe', [line('day', 'park', condition('day_at_least', count=3))]), member('yuna')],
        [{'id': 'meet', 'name': '첫 만남', 'scene': {'text': '...', 'cast': ['mina']}, 'repeat': False}],
    )

    assert [cast.id for cast in read.cast] == ['mina', 'yuna']
    assert read.member('mina').home == 'cafe'
    schedule = read.member('mina').schedule[0]
    assert (schedule.slot, schedule.place, schedule.when.match) == ('day', 'park', Match.ALL)
    assert schedule.when.items[0].kind == ConditionKind.DAY_AT_LEAST
    assert [stage.at for stage in read.member('mina').affection.stages] == [0, 30, 70]
    assert read.event('meet').scene.cast == ('mina',)
    assert (read.member('nobody'), read.event('nothing')) == (None, None)


def test_a_format_one_world_has_no_events():
    body = document([member('mina')], format=1)
    del body['events'], body['endings']

    assert read_world(body).events == ()


def test_a_condition_without_unused_fields_is_read():
    read = read_world(document([member('mina', schedule=[line('day', 'park', {'kind': 'slot_is', 'target': 'day'})])]))

    only = read.member('mina').schedule[0].when.items[0]
    assert (only.target, only.value, only.count) == ('day', None, 1)


def test_the_start_state_comes_from_the_world():
    read = world(
        [member('mina', start=10), member('yuna', start=40)],
        start_items=[{'item': 'ticket', 'count': 1}, {'item': 'ticket', 'count': 2}, {'item': 'map', 'count': 1}],
    )

    state = start_state(read)

    assert (state.day, state.slot, state.place) == (1, 'morning', 'home')
    assert dict(state.items) == {'ticket': 3, 'map': 1}
    assert dict(state.affection) == {'mina': 10, 'yuna': 40}
    assert (state.gifts, state.seen, state.companions) == (frozenset(), frozenset(), ())


def test_the_state_cannot_be_changed():
    state = start_state(world([member('mina')]))

    with pytest.raises(dataclasses.FrozenInstanceError):
        state.day = 2  # type: ignore[misc]
    with pytest.raises(TypeError):
        state.affection['mina'] = 99  # type: ignore[index]
