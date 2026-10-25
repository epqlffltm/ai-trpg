# story-server/tests/test_engine_conditions.py

"""
조건 맞추기(app/engine/conditions.py)를 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 종류마다 맞는 경우와 맞지 않는 경우
  - 호감도는 단계의 경계값으로 본다(이상, 아래). 없는 단계나 없는 인물이면 맞지 않는다.
    상태에 호감도가 없는 인물은 판의 시작 값이다
  - 목록: 비면 맞는다. 모두(all)는 다 맞아야, 하나라도(any)는 하나만 맞으면 된다
"""

from dataclasses import replace
from types import MappingProxyType

import pytest

from app.engine.conditions import is_met, match_conditions
from app.engine.state import StoryState, start_state
from app.engine.world import Condition, Conditions
from tests.engine_worlds import clock, member, world

WORLD = world([member('mina', start=10), member('yuna', start=50)])
START = start_state(WORLD)


def state(**changes) -> StoryState:
    """처음의 상태에서 몇 칸을 바꾼 상태. items 와 affection 은 dict 로 준다."""
    for name in ('items', 'affection'):
        if name in changes:
            changes[name] = MappingProxyType(changes[name])
    return replace(START, **changes)


def met(kind: str, now: StoryState, target: str | None = None, value: str | None = None, count: int = 1) -> bool:
    return is_met(Condition(kind=kind, target=target, value=value, count=count), now, WORLD)


@pytest.mark.parametrize(
    ('kind', 'target', 'value', 'count', 'yes', 'no'),
    [
        ('reach_place', 'home', None, 1, state(), state(place='cafe')),
        ('hold_item', 'ticket', None, 2, state(items={'ticket': 2}), state(items={'ticket': 1})),
        ('gave_item', 'mina', 'flower', 1, state(gifts=frozenset({('mina', 'flower')})), state()),
        ('day_at_least', None, None, 3, state(minutes=clock(3, 8)), state(minutes=clock(2, 23))),
        ('day_at_most', None, None, 3, state(minutes=clock(3, 23)), state(minutes=clock(4, 8))),
        ('slot_is', 'night', None, 1, state(minutes=clock(1, 20)), state()),
        ('accompanied', 'mina', None, 1, state(companions=('yuna', 'mina')), state(companions=('yuna',))),
        ('event_seen', 'meet', None, 1, state(seen=frozenset({'meet'})), state()),
    ],
)
def test_each_kind(kind: str, target, value, count: int, yes: StoryState, no: StoryState):
    assert met(kind, yes, target, value, count) is True
    assert met(kind, no, target, value, count) is False


def test_holding_nothing_is_holding_zero():
    assert met('hold_item', state(), 'ticket') is False


@pytest.mark.parametrize(
    ('affection', 'at_least_friend', 'below_friend'),
    [(29, False, True), (30, True, False), (100, True, False)],
)
def test_affection_is_seen_by_the_stage_floor(affection: int, at_least_friend: bool, below_friend: bool):
    now = state(affection={'mina': affection})

    assert met('affection_at_least', now, 'mina', '친함') is at_least_friend
    assert met('affection_below', now, 'mina', '친함') is below_friend


def test_affection_missing_from_the_state_is_the_start_value():
    now = state(affection={})

    assert met('affection_at_least', now, 'yuna', '친함') is True
    assert met('affection_below', now, 'mina', '친함') is True


@pytest.mark.parametrize('kind', ['affection_at_least', 'affection_below'])
@pytest.mark.parametrize(('target', 'value'), [('mina', '원수'), ('nobody', '친함')])
def test_an_unknown_stage_or_person_is_not_met(kind: str, target: str, value: str):
    assert met(kind, state(), target, value) is False


def conditions(match: str, *items: tuple[str, str | None]) -> Conditions:
    return Conditions(match=match, items=tuple(Condition(kind=kind, target=target) for kind, target in items))


def test_an_empty_list_is_met():
    assert match_conditions(Conditions(), state(), WORLD) is True
    assert match_conditions(Conditions(match='any'), state(), WORLD) is True


@pytest.mark.parametrize(
    ('match', 'expected'),
    [('all', False), ('any', True)],
)
def test_all_or_any(match: str, expected: bool):
    # 집에 있다(맞다), 밤이다(아니다)
    both = conditions(match, ('reach_place', 'home'), ('slot_is', 'night'))

    assert match_conditions(both, state(), WORLD) is expected


def test_all_is_met_when_every_one_is():
    both = conditions('all', ('reach_place', 'home'), ('slot_is', 'morning'))

    assert match_conditions(both, state(), WORLD) is True
