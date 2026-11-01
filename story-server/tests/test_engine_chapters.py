# story-server/tests/test_engine_chapters.py

"""
장(app/engine/chapters.py, docs/architecture/chapters.md)을 검증한다. 순수 함수라 DB 도 앱도 없다.

보는 것.
  - 장이 없는 판은 지금과 같다(장이 없고 모두 열려 있다)
  - 장이 있는 판은 첫 장에서 시작한다. 어느 장에도 적지 않은 것은 처음부터 열려 있다
  - 닫힌 장소로는 가지 못하고, 닫힌 이벤트는 조건이 맞아도 열리지 않는다. 효과의 move_to 는 닫힌 장소로 옮기지 않는다
  - 행동의 맨 끝에 다음 장의 조건을 본다. 한 번에 한 장만 넘어가고, 새로 열린 이벤트는 다음 행동부터 본다
  - 엔딩을 본 행동에서도 장은 넘어간다
  - 조건 chapter_at_least 는 지금 장이 그 장이거나 그 뒤일 때 맞는다. 없는 장이면 맞지 않는다
  - 지금 장은 저장한 상태에 적힌다. 장이 없던 때의 상태는 첫 장으로 읽는다
"""

import pytest

from app.engine.actions import CannotMove
from app.engine.conditions import is_met
from app.engine.play import Move, PassTime, play
from app.engine.state import start_state
from app.engine.world import Condition, ConditionKind
from app.turns.states import state_from_json, state_on_path, state_to_json
from tests.engine_worlds import condition, effect, ending, event, world

PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}, {'a': 'home', 'b': 'square', 'minutes': 30}]


def chapter(chapter_id: str, *items: dict, places: list[str] | None = None, events: list[str] | None = None) -> dict:
    """장 하나. 조건은 items 다."""
    return {
        'id': chapter_id,
        'name': f'{chapter_id} 의 이름',
        'when': {'match': 'all', 'items': list(items)},
        'opens': {'places': places or [], 'events': events or []},
    }


# 1장(여름의 시작)에서 해변에 가면 2장(축제)이 열린다. 2장은 광장과 축제를 연다
SUMMER = chapter('summer')
FESTIVAL = chapter('festival', condition('reach_place', 'beach'), places=['square'], events=['parade'])
PARADE = event('parade', condition('reach_place', 'beach'))


def chaptered(*chapters: dict, events: list[dict] | None = None, **fields):
    return world(events=events or [], paths=PATHS, chapters=list(chapters), **fields)


def test_a_world_without_chapters_is_as_before():
    plain = world(paths=PATHS)
    state = start_state(plain)

    played = play(plain, state, Move('square'))

    assert (state.chapter, played.chapter, played.state.chapter) == (None, None, None)
    assert played.state.place == 'square'


def test_it_starts_in_the_first_chapter_and_unlisted_places_are_open():
    rules = chaptered(SUMMER, FESTIVAL)
    state = start_state(rules)

    assert state.chapter == 'summer'
    assert (rules.place_open('beach', 'summer'), rules.place_open('square', 'summer')) == (True, False)
    assert rules.place_open('square', 'festival')


def test_a_closed_place_cannot_be_entered():
    rules = chaptered(SUMMER, FESTIVAL)

    with pytest.raises(CannotMove):
        play(rules, start_state(rules), Move('square'))


def test_the_chapter_advances_at_the_end_and_new_events_wait_for_the_next_action():
    rules = chaptered(SUMMER, FESTIVAL, events=[PARADE])

    moved = play(rules, start_state(rules), Move('beach'))
    waited = play(rules, moved.state, PassTime())

    # 축제의 조건(해변)은 이동한 행동에서도 맞지만 그때는 아직 1장이라 열리지 않는다
    assert (moved.chapter.id, moved.event, moved.state.chapter) == ('festival', None, 'festival')
    assert (waited.chapter, waited.event.id) == (None, 'parade')
    assert play(rules, waited.state, Move('home')).state.place == 'home'


def test_only_one_chapter_at_a_time():
    finale = chapter('finale', condition('reach_place', 'beach'))
    rules = chaptered(SUMMER, FESTIVAL, finale)

    moved = play(rules, start_state(rules), Move('beach'))
    waited = play(rules, moved.state, PassTime())
    again = play(rules, waited.state, PassTime())

    assert [moved.state.chapter, waited.state.chapter, again.state.chapter] == ['festival', 'finale', 'finale']
    assert (waited.chapter.id, again.chapter) == ('finale', None)


def test_a_closed_event_does_not_open_even_when_its_conditions_hold():
    early = event('early', condition('reach_place', 'beach'))
    locked = chapter('locked', condition('day_at_least', count=9), events=['early'])
    rules = chaptered(SUMMER, locked, events=[early])

    played = play(rules, start_state(rules), Move('beach'))

    assert (played.event, played.state.seen) == (None, frozenset())


def test_move_to_a_closed_place_is_skipped_but_other_effects_apply():
    lift = event(
        'lift',
        condition('reach_place', 'beach'),
        on_open=[effect('move_to', 'square'), effect('give_item', 'shell', 1)],
    )
    rules = chaptered(SUMMER, FESTIVAL, events=[lift])

    played = play(rules, start_state(rules), Move('beach'))

    assert played.event.id == 'lift'
    assert (played.state.place, dict(played.state.items)) == ('beach', {'shell': 1})


def test_the_chapter_still_advances_on_an_action_that_reaches_an_ending():
    fireworks = event('fireworks', condition('reach_place', 'beach'))
    rules = chaptered(SUMMER, FESTIVAL, events=[fireworks], endings=[ending('end', 'event', 'fireworks')])

    played = play(rules, start_state(rules), Move('beach'))

    assert (played.ending.id, played.chapter.id, played.state.chapter) == ('end', 'festival', 'festival')


@pytest.mark.parametrize(
    ('now', 'target', 'expected'),
    [
        ('summer', 'summer', True),
        ('summer', 'festival', False),
        ('festival', 'summer', True),
        ('festival', 'gone', False),
    ],
)
def test_chapter_at_least(now: str, target: str, expected: bool):
    rules = chaptered(SUMMER, FESTIVAL)
    state = start_state(rules)
    state = state_from_json({**state_to_json(state), 'chapter': now})

    assert is_met(Condition(kind=ConditionKind.CHAPTER_AT_LEAST, target=target), state, rules) is expected


def test_the_chapter_is_stored_and_old_states_read_as_the_first_chapter():
    rules = chaptered(SUMMER, FESTIVAL)
    moved = play(rules, start_state(rules), Move('beach')).state
    old = {key: value for key, value in state_to_json(moved).items() if key != 'chapter'}

    assert state_on_path(rules, [state_to_json(moved)]).chapter == 'festival'
    assert state_on_path(rules, [old]).chapter is None
    assert (rules.place_open('square', None), rules.reached_index(None)) == (False, 0)
