# story-server/tests/test_engine_play.py

"""
행동 하나를 끝까지 판정하는 것(app/engine/play.py)을 검증한다. 순수 함수라 DB 도 앱도 없다.

보는 것.
  - 이동, 시간, 하루 마치기는 기다리던 선택지를 지우고 시각을 흘린다. 그 뒤에 기한을 보고, 지났으면 기한의 엔딩이다
  - 선택지 고르기는 그 효과를 반영한다. 시각이 흐르지 않아 기한을 보지 않는다
  - 행동 뒤에 열 수 있는 이벤트를 하나 연다. 그 이벤트로 시작되는 엔딩이 있으면 본다
  - 고백이 엔딩을 보면 거기서 끝이다(이벤트를 열지 않는다). 계속하는 실패면 이벤트를 본다
  - 엔딩을 본 뒤(후일담)에도 이벤트는 열리지만 엔딩은 다시 일어나지 않는다
  - 할 수 없는 행동은 각 모듈의 예외다
"""

import pytest

from app.engine.actions import CannotMove
from app.engine.confession import ConfessionRefused
from app.engine.events import ChoiceRefused
from app.engine.play import Choose, Confess, EndDay, Move, PassTime, play
from app.engine.state import StoryState, start_state
from tests.engine_worlds import clock, condition, confession, effect, ending, event, member, world

PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}]


def test_a_move_drops_a_waiting_choice_and_opens_an_event():
    rain = event('rain', condition('reach_place', 'beach'), choices=[{'id': 'run', 'text': '뛴다', 'effects': []}])
    played_world = world(events=[rain], paths=PATHS)
    state = StoryState(minutes=clock(1, 7), place='home', choosing='old')

    played = play(played_world, state, Move('beach'))

    assert (played.state.place, played.state.minutes) == ('beach', clock(1, 7, 30))
    assert played.event.id == 'rain'
    # 옛 선택지는 사라지고 새 이벤트의 선택지를 기다린다
    assert (played.state.choosing, played.state.seen) == ('rain', frozenset({'rain'}))
    assert played.ending is None


def test_time_past_the_deadline_reaches_the_deadline_ending():
    played_world = world(deadline_days=1, endings=[ending('solo', 'deadline')], events=[event('never')])

    played = play(played_world, StoryState(minutes=clock(1, 19), place='home'), EndDay())

    assert (played.ending.id, played.state.ending) == ('solo', 'solo')
    # 엔딩을 보면 이벤트를 열지 않는다
    assert played.event is None


def test_time_before_the_deadline_has_no_ending():
    played_world = world(deadline_days=2, endings=[ending('solo', 'deadline')])

    played = play(played_world, StoryState(minutes=clock(1, 7), place='home'), PassTime())

    assert played.ending is None
    assert played.state.minutes == clock(1, 12)


def test_a_choice_applies_its_effects_and_does_not_look_at_the_deadline():
    gift = event('gift', choices=[{'id': 'take', 'text': '받는다', 'effects': [effect('give_item', 'shell', 2)]}])
    played_world = world(events=[gift], deadline_days=1, endings=[ending('solo', 'deadline')])
    state = StoryState(minutes=clock(2, 7), place='home', choosing='gift', seen=frozenset({'gift'}))

    played = play(played_world, state, Choose('take'))

    assert (played.choice.id, played.state.items['shell'], played.state.choosing) == ('take', 2, None)
    assert played.ending is None


def test_an_event_can_start_an_ending():
    farewell = event('farewell', condition('day_at_least', count=2))
    played_world = world(events=[farewell], endings=[ending('parting', 'event', 'farewell')])

    played = play(played_world, StoryState(minutes=clock(1, 19), place='home'), EndDay())

    assert (played.event.id, played.ending.id, played.state.ending) == ('farewell', 'parting', 'parting')


def test_a_successful_confession_ends_without_opening_events():
    mina = member('mina', home='home', start=80, confession=confession('연인'))
    played_world = world([mina], events=[event('after')], endings=[ending('with_mina', 'confess_success', 'mina')])

    played = play(played_world, start_state(played_world), Confess('mina'))

    assert (played.accepted, played.ending.id, played.event) == (True, 'with_mina', None)


def test_a_failed_confession_that_continues_still_opens_events():
    mina = member('mina', home='home', start=10, confession=confession('연인'))
    played_world = world([mina], events=[event('sulk')])

    played = play(played_world, start_state(played_world), Confess('mina'))

    assert (played.accepted, played.ending, played.event.id) == (False, None, 'sulk')
    assert played.state.affection['mina'] == 0


def test_in_an_epilogue_events_open_but_endings_do_not_happen_again():
    played_world = world(
        events=[event('festa')],
        deadline_days=1,
        endings=[ending('solo', 'deadline'), ending('again', 'event', 'festa')],
    )
    state = StoryState(minutes=clock(3, 7), place='home', ending='solo')

    played = play(played_world, state, PassTime())

    assert (played.event.id, played.ending, played.state.ending) == ('festa', None, 'solo')


@pytest.mark.parametrize(
    ('action', 'error'),
    [
        (Move('home'), CannotMove),
        (Move('nowhere'), CannotMove),
        (Choose('nothing'), ChoiceRefused),
        (Confess('nobody'), ConfessionRefused),
    ],
)
def test_impossible_actions_raise(action, error):
    played_world = world(paths=PATHS)

    with pytest.raises(error):
        play(played_world, start_state(played_world), action)
