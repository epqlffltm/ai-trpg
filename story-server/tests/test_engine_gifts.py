# story-server/tests/test_engine_gifts.py

"""
건네기(app/engine/gifts.py)와, 행동으로서의 건네기(app/engine/play.py 의 Give)를 검증한다. 순수 함수라 DB 도 앱도 없다.

보는 것.
  - 물건이 하나 줄고(다 주면 소지품에서 빠진다) 건넨 적이 있는 (인물, 물건)에 든다
  - 그 물건의 규칙들을 차례로 더해 호감도를 바꾸고, 더할 때마다 0~100 안으로 자른다(chat 과 같다).
    맞는 규칙이 없으면 그대로다
  - once 인 규칙은 그 인물에게 그 물건을 처음 건넬 때만 든다. 다른 인물에게 건넨 것은 상관없다
  - 장면에 없는 인물, 없는 물건은 받지 않는다
  - 행동으로서는 기다리던 선택지를 지우고, 시각이 흐르지 않아 기한을 보지 않고, 이벤트(gave_item)를 연다.
    후일담에도 된다
"""

from types import MappingProxyType

import pytest

from app.engine.gifts import GiftRefusal, GiftRefused, give
from app.engine.play import Give, play
from app.engine.state import StoryState
from tests.engine_worlds import clock, condition, ending, event, gift, member, world

FLOWER_RULES = [gift('likes', 'flower', 10), gift('first', 'flower', 5, once=True)]


def holding(items: dict[str, int], **fields) -> StoryState:
    return StoryState(minutes=clock(1, 7), place='home', items=MappingProxyType(items), **fields)


def test_giving_hands_over_one_item_and_remembers_it():
    played_world = world([member('mina', home='home')])

    given = give(played_world, holding({'flower': 2}), 'mina', 'flower', ['mina'])

    assert (dict(given.state.items), given.state.gifts) == ({'flower': 1}, frozenset({('mina', 'flower')}))
    # 맞는 규칙이 없다. 호감도는 그대로다
    assert (given.change, given.state.affection.get('mina')) == (0, None)


def test_the_last_one_leaves_the_bag():
    played_world = world([member('mina', home='home')])

    given = give(played_world, holding({'flower': 1, 'shell': 1}), 'mina', 'flower', ['mina'])

    assert dict(given.state.items) == {'shell': 1}


def test_the_first_gift_adds_every_matching_rule():
    played_world = world([member('mina', home='home', start=20, gifts=FLOWER_RULES)])

    given = give(played_world, holding({'flower': 1}), 'mina', 'flower', ['mina'])

    assert (given.change, given.state.affection['mina']) == (15, 35)


def test_a_once_rule_does_not_count_again():
    played_world = world([member('mina', home='home', start=20, gifts=FLOWER_RULES)])
    state = holding({'flower': 1}, gifts=frozenset({('mina', 'flower')}))

    given = give(played_world, state, 'mina', 'flower', ['mina'])

    assert (given.change, given.state.affection['mina']) == (10, 30)


def test_a_gift_to_someone_else_does_not_use_up_the_once_rule():
    played_world = world([member('mina', home='home', gifts=FLOWER_RULES), member('jun', home='home')])
    state = holding({'flower': 1}, gifts=frozenset({('jun', 'flower')}))

    assert give(played_world, state, 'mina', 'flower', ['mina', 'jun']).change == 15


@pytest.mark.parametrize(
    ('start', 'rules', 'after'),
    [
        (95, [gift('a', 'ring', 30)], 100),
        (5, [gift('b', 'ring', -20)], 0),
        # 차례로 자른다. 95 +10 → 100(잘림) -10 → 90. 합(0)을 한 번에 더하면 95 다
        (95, [gift('c', 'ring', 10), gift('d', 'ring', -10)], 90),
    ],
)
def test_affection_stays_between_0_and_100(start: int, rules: list, after: int):
    played_world = world([member('mina', home='home', start=start, gifts=rules)])

    given = give(played_world, holding({'ring': 1}), 'mina', 'ring', ['mina'])

    assert given.state.affection['mina'] == after


@pytest.mark.parametrize(
    ('cast', 'items', 'reason'),
    [('jun', {'flower': 1}, GiftRefusal.NOT_IN_SCENE), ('mina', {}, GiftRefusal.NOT_HELD)],
)
def test_refused_gifts(cast: str, items: dict, reason: GiftRefusal):
    played_world = world([member('mina', home='home'), member('jun', home='beach')])

    with pytest.raises(GiftRefused) as refused:
        give(played_world, holding(items), cast, 'flower', ['mina'])

    assert refused.value.reason == reason


# --- 행동으로서 ---


def test_a_gift_drops_the_waiting_choice_and_opens_an_event():
    thanks = event('thanks', condition('gave_item', 'mina', 'flower'))
    played_world = world([member('mina', home='home', gifts=FLOWER_RULES)], events=[thanks])
    state = holding({'flower': 1}, choosing='old')

    played = play(played_world, state, Give('mina', 'flower'))

    assert (played.affection_change, played.event.id, played.state.choosing) == (15, 'thanks', None)


def test_a_gift_lets_no_time_pass_so_the_deadline_does_not_end_it():
    played_world = world([member('mina', home='home')], deadline_days=1, endings=[ending('solo', 'deadline')])
    state = StoryState(minutes=clock(2, 7), place='home', items=MappingProxyType({'flower': 1}))

    played = play(played_world, state, Give('mina', 'flower'))

    assert (played.ending, played.state.minutes) == (None, clock(2, 7))


def test_gifts_still_work_in_an_epilogue():
    played_world = world([member('mina', home='home', gifts=FLOWER_RULES)])

    played = play(played_world, holding({'flower': 1}, ending='solo'), Give('mina', 'flower'))

    assert played.state.affection['mina'] == 15
