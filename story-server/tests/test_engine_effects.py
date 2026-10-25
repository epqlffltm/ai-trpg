# story-server/tests/test_engine_effects.py

"""
효과의 반영(app/engine/effects.py)을 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 호감도: ±n 을 더하고 0~100 안으로 자른다. 한 목록에 여러 인물. 상태에 없으면 판의 시작 값에서 바꾼다
  - 물건: 주면 더하고, 가져가면 가진 만큼까지 빼고 0 이면 소지품에서 뺀다
  - 동행: 시작하면 시작한 차례로 붙고(이미 있으면 그대로), 끝내면 빠진다(없으면 그대로)
  - 장소 옮기기: 장소만 바꾼다(시간은 흐르지 않는다). 동행은 따라온다
  - 목록은 적힌 차례대로다. 앞의 효과가 바꾼 것을 뒤의 효과가 본다. 반영은 처음의 상태를 바꾸지 않는다
  - 판의 효과 칸을 그대로 읽는다(모르는 칸은 버린다)
"""

from dataclasses import replace
from types import MappingProxyType

import pytest

from app.engine.effects import Effect, apply_effect, apply_effects
from app.engine.scene import scene_cast
from app.engine.state import StoryState, start_state
from tests.engine_worlds import member, world

WORLD = world([member('mina', 'cafe', start=10), member('yuna', 'home', start=95)])
START = start_state(WORLD)


def effect(kind: str, target: str, amount: int | None = None) -> Effect:
    return Effect(kind=kind, target=target, amount=amount)


def with_items(**items: int) -> StoryState:
    return replace(START, items=MappingProxyType(items))


@pytest.mark.parametrize(('amount', 'expected'), [(5, 15), (-5, 5), (-50, 0), (100, 100)])
def test_affection_changes_within_the_range(amount: int, expected: int):
    changed = apply_effect(effect('affection', 'mina', amount), START, WORLD)

    assert changed.affection['mina'] == expected
    assert changed.affection['yuna'] == 95


def test_several_people_change_in_one_list():
    # 질투: 미나가 오르고 유나가 내린다
    changed = apply_effects([effect('affection', 'mina', 20), effect('affection', 'yuna', -10)], START, WORLD)

    assert dict(changed.affection) == {'mina': 30, 'yuna': 85}


def test_affection_missing_from_the_state_starts_from_the_world():
    empty = replace(START, affection=MappingProxyType({}))

    assert apply_effect(effect('affection', 'yuna', 10), empty, WORLD).affection['yuna'] == 100


def test_items_are_given_and_taken():
    given = apply_effect(effect('give_item', 'rose', 2), with_items(rose=1), WORLD)
    taken = apply_effect(effect('take_item', 'rose', 2), with_items(rose=3, map=1), WORLD)
    new = apply_effect(effect('give_item', 'key', 1), with_items(), WORLD)

    assert (dict(given.items), dict(taken.items), dict(new.items)) == ({'rose': 3}, {'rose': 1, 'map': 1}, {'key': 1})


@pytest.mark.parametrize('held', [{'rose': 2}, {'rose': 1}, {}])
def test_taking_more_than_held_takes_what_there_is(held: dict):
    taken = apply_effect(effect('take_item', 'rose', 2), with_items(map=1, **held), WORLD)

    assert dict(taken.items) == {'map': 1}


def test_accompanying_starts_in_order_and_ends():
    started = apply_effects(
        [effect('accompany_start', 'yuna'), effect('accompany_start', 'mina'), effect('accompany_start', 'yuna')],
        START,
        WORLD,
    )
    ended = apply_effects([effect('accompany_end', 'yuna'), effect('accompany_end', 'sora')], started, WORLD)

    assert (started.companions, ended.companions) == (('yuna', 'mina'), ('mina',))


def test_moving_changes_only_the_place_and_companions_follow():
    together = replace(START, companions=('mina',))

    moved = apply_effect(effect('move_to', 'beach'), together, WORLD)

    assert replace(moved, place=together.place) == together
    assert moved.place == 'beach'
    assert scene_cast(WORLD, moved) == ['mina']


def test_a_list_applies_in_order():
    # 장미를 받아 바로 건네주는 이벤트: 준 뒤 가져가므로 남지 않는다
    after = apply_effects([effect('give_item', 'rose', 1), effect('take_item', 'rose', 1)], with_items(), WORLD)
    # 거꾸로면 가져갈 것이 없고 받은 것이 남는다
    reversed_after = apply_effects(
        [effect('take_item', 'rose', 1), effect('give_item', 'rose', 1)], with_items(), WORLD
    )

    assert (dict(after.items), dict(reversed_after.items)) == ({}, {'rose': 1})


def test_applying_leaves_the_old_state_alone():
    apply_effects([effect('affection', 'mina', 50), effect('give_item', 'rose', 1)], START, WORLD)

    assert (START.affection['mina'], dict(START.items)) == (10, {})


def test_an_empty_list_changes_nothing():
    assert apply_effects([], START, WORLD) == START


def test_the_worlds_effect_fields_are_read():
    read = Effect.model_validate({'kind': 'accompany_start', 'target': 'mina', 'amount': None, 'note': 'x'})

    assert (read.kind, read.target, read.amount) == ('accompany_start', 'mina', None)
