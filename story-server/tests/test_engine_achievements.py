# story-server/tests/test_engine_achievements.py

"""
업적을 주는 엔진(app/engine/achievements.py)과 판의 업적의 칸(app/engine/world.py)을 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 조건이 맞는 업적을 판의 차례로 준다. 이미 받은 것은 주지 않는다. 조건이 빈 업적은 주지 않는다
  - "모두"와 "하나라도"는 이벤트의 조건과 같다
  - 엔딩을 봤다(ending_seen)는 이 가지에서 방금 닿은 엔딩도 본 것으로 친다. 세션을 시작할 때의 기록도 그대로 본다
  - 업적이 없는 판(형식 8 까지)은 업적이 빈 것으로 읽는다. 숨김과 그림을 읽는다
"""

import uuid
from dataclasses import replace

from app.engine.achievements import is_earned, newly_earned, with_reached_ending
from app.engine.state import start_state
from tests.engine_worlds import condition, document, member, world

PICTURE = uuid.UUID('aaaaaaaa-1111-4222-8333-444444444444')


def achievement(achievement_id: str, *items: dict, match: str = 'all', **fields) -> dict:
    """업적 하나. 조건은 items 다."""
    return {
        'id': achievement_id,
        'name': f'{achievement_id} 업적',
        'description': '',
        'hidden': False,
        'image_id': None,
        'when': {'match': match, 'items': list(items)},
        **fields,
    }


BEACH = achievement('beach', condition('reach_place', 'beach'))
SHELLS = achievement('shells', condition('hold_item', 'shell', count=3))
EITHER = achievement('either', condition('reach_place', 'beach'), condition('hold_item', 'shell'), match='any')
BOTH = achievement('both', condition('reach_place', 'beach'), condition('hold_item', 'shell'))
EMPTY = achievement('empty')
SOLO = achievement('solo-seen', condition('ending_seen', 'solo'), hidden=True, image_id=str(PICTURE))
WORLD = world([member('mina', 'home')], achievements=[BEACH, SHELLS, EITHER, BOTH, EMPTY, SOLO])
START = start_state(WORLD)


def ids(found) -> list[str]:
    return [one.id for one in found]


def test_gives_the_met_ones_in_the_order_of_the_world():
    at_beach = replace(START, place='beach')

    assert ids(newly_earned(WORLD, at_beach, frozenset())) == ['beach', 'either']


def test_does_not_give_what_is_already_owned():
    at_beach = replace(START, place='beach')

    assert ids(newly_earned(WORLD, at_beach, frozenset({'beach'}))) == ['either']


def test_all_and_any_are_the_same_as_events():
    holding = replace(START, place='beach', items={'shell': 3})

    assert ids(newly_earned(WORLD, holding, frozenset())) == ['beach', 'shells', 'either', 'both']


def test_an_achievement_without_conditions_is_never_given():
    assert is_earned(WORLD.achievements[4], START, WORLD) is False
    assert newly_earned(WORLD, START, frozenset()) == ()


def test_an_ending_reached_in_this_branch_counts_as_seen():
    reached = replace(START, ending='solo')

    assert ids(newly_earned(WORLD, reached, frozenset())) == ['solo-seen']
    assert with_reached_ending(reached).cleared == frozenset({'solo'})
    # 닿은 엔딩이 없으면 상태 그대로다
    assert with_reached_ending(START) is START


def test_an_ending_seen_before_the_session_also_counts():
    cleared = replace(START, cleared=frozenset({'solo'}))

    assert ids(newly_earned(WORLD, cleared, frozenset())) == ['solo-seen']


def test_reads_hidden_and_picture_and_a_world_without_achievements_has_none():
    solo = WORLD.achievements[5]

    assert (solo.hidden, solo.image_id, solo.name) == (True, PICTURE, 'solo-seen 업적')
    assert world([member('mina', 'home')]).achievements == ()
    assert 'achievements' not in document()
