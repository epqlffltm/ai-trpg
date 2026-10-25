# story-server/tests/test_engine_events.py

"""
이벤트 열기와 선택지(app/engine/events.py)를 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 조건이 맞는 것 가운데 판의 차례로 하나만 연다. 조건이 없으면 늘 맞는다. 열 것이 없으면 그대로다
  - 한 번만인 이벤트는 다시 열리지 않는다. 되풀이는 다시 열린다
  - 열리면 본 이벤트에 넣고 열릴 때의 효과를 반영한다. 그 효과로 다른 이벤트의 조건이 맞아도 같은 행동에는 열지 않는다
  - 선택지가 있으면 고르기를 기다린다. 고르면 그 효과를 반영하고 기다림을 끝낸다. 고른 뒤에도 다음 이벤트를 본다
  - 기다리는 이벤트가 없거나 없는 선택지면 ChoiceRefused. 고르지 않고 넘어가면 선택지가 사라지고 효과는 없다
  - 이벤트가 부른 인물은 장면에 들어온다
  - 판의 이벤트(장면, 효과, 선택지)를 읽는다
"""

from dataclasses import replace

import pytest

from app.engine.events import ChoiceRefused, choose, drop_choice, next_event, open_event, open_next_event
from app.engine.scene import scene_cast
from app.engine.state import start_state
from tests.engine_worlds import condition, effect, event, member, world

CAST = [member('mina', 'cafe', start=10), member('yuna', 'library')]


def opened_ids(events: list[dict], state=None) -> str | None:
    read = world(CAST, events)
    found = next_event(read, state or start_state(read))
    return found.id if found is not None else None


def test_the_first_matching_event_in_order_opens():
    events = [
        event('cafe-talk', condition('reach_place', 'cafe')),
        event('morning', condition('slot_is', 'morning')),
        event('home', condition('reach_place', 'home')),
    ]

    assert opened_ids(events) == 'morning'


def test_without_conditions_it_always_opens_and_nothing_opens_when_nothing_matches():
    assert opened_ids([event('free')]) == 'free'
    assert opened_ids([event('far', condition('reach_place', 'moon'))]) is None


def test_a_one_time_event_does_not_open_again_but_a_repeating_one_does():
    once, again = world(CAST, [event('once')]), world(CAST, [event('again', repeat=True)])

    once_after, _ = open_next_event(once, start_state(once))
    again_after, _ = open_next_event(again, start_state(again))

    assert next_event(once, once_after) is None
    assert next_event(again, again_after).id == 'again'


def test_opening_records_it_and_applies_its_effects():
    read = world(CAST, [event('gift', on_open=[effect('give_item', 'rose', 1), effect('affection', 'mina', 5)])])

    after, opened = open_next_event(read, start_state(read))

    assert opened.id == 'gift'
    assert (after.seen, dict(after.items), after.affection['mina'], after.choosing) == (
        frozenset({'gift'}),
        {'rose': 1},
        15,
        None,
    )


def test_nothing_to_open_leaves_the_state_alone():
    read = world(CAST, [event('far', condition('reach_place', 'moon'))])
    start = start_state(read)

    assert open_next_event(read, start) == (start, None)


def test_one_action_opens_one_event_even_if_its_effects_open_another():
    read = world(
        CAST,
        [event('first', on_open=[effect('give_item', 'key', 1)]), event('second', condition('hold_item', 'key'))],
    )

    after, opened = open_next_event(read, start_state(read))

    assert (opened.id, after.seen) == ('first', frozenset({'first'}))
    assert next_event(read, after).id == 'second'


CHOICES = [
    {'id': 'accept', 'text': '받는다', 'effects': [effect('affection', 'mina', 10)]},
    {'id': 'refuse', 'text': '거절한다', 'effects': [effect('affection', 'mina', -5)]},
]


def test_an_event_with_choices_waits_and_a_choice_applies():
    read = world(CAST, [event('offer', choices=CHOICES)])
    waiting, _ = open_next_event(read, start_state(read))

    chosen, choice = choose(read, waiting, 'accept')

    assert waiting.choosing == 'offer'
    assert (choice.text, chosen.affection['mina'], chosen.choosing) == ('받는다', 20, None)


def test_choosing_is_an_action_so_the_next_event_can_open():
    read = world(CAST, [event('offer', choices=CHOICES), event('thanks', condition('event_seen', 'offer'))])
    waiting, _ = open_next_event(read, start_state(read))

    chosen, _ = choose(read, waiting, 'refuse')

    assert next_event(read, chosen).id == 'thanks'


@pytest.mark.parametrize('choice_id', ['accept', 'nothing'])
def test_a_choice_without_a_waiting_event_is_refused(choice_id: str):
    read = world(CAST, [event('offer', choices=CHOICES)])

    with pytest.raises(ChoiceRefused):
        choose(read, start_state(read), choice_id)


def test_a_choice_the_event_does_not_have_is_refused():
    read = world(CAST, [event('offer', choices=CHOICES)])
    waiting, _ = open_next_event(read, start_state(read))

    with pytest.raises(ChoiceRefused):
        choose(read, waiting, 'run')


def test_moving_on_drops_the_choice_without_its_effects():
    read = world(CAST, [event('offer', choices=CHOICES)])
    waiting, _ = open_next_event(read, start_state(read))

    dropped = drop_choice(waiting)

    assert replace(dropped, choosing='offer') == waiting
    with pytest.raises(ChoiceRefused):
        choose(read, dropped, 'accept')


def test_opening_another_event_replaces_the_waiting_one():
    read = world(CAST, [event('offer', choices=CHOICES), event('plain', repeat=True)])
    waiting, _ = open_next_event(read, start_state(read))

    replaced = open_event(read, waiting, read.event('plain'))

    assert replaced.choosing is None


def test_the_people_an_event_calls_join_the_scene():
    read = world(CAST, [event('meet', cast=['yuna'])])
    after, opened = open_next_event(read, start_state(read))

    assert scene_cast(read, after) == []
    assert scene_cast(read, after, called=opened.scene.cast) == ['yuna']


def test_the_worlds_event_fields_are_read():
    read = world(CAST, [event('offer', condition('day_at_least', count=2), cast=['mina'], choices=CHOICES)])

    offer = read.event('offer')
    assert (offer.name, offer.repeat, offer.scene.text, offer.scene.cast) == (
        'offer',
        False,
        'offer 의 장면.',
        ('mina',),
    )
    assert [(choice.id, len(choice.effects)) for choice in offer.choices] == [('accept', 1), ('refuse', 1)]
    assert offer.choices[0].effects[0].amount == 10
