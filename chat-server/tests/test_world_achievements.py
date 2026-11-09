# chat-server/tests/test_world_achievements.py

"""
업적을 주는 엔진(app/world/achievements.py)과 판의 업적의 칸(app/assets/schemas.py)을 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 종류마다 맞추는 법: 가 본 장소, 가진 물건의 수, 받은 물건, 호감도의 단계, 나온 이벤트 씬, 보낸 말의 수
  - 모두(all)와 하나라도(any). 조건이 빈 업적과 모르는 종류는 맞지 않는다. 이미 받은 것은 주지 않는다. 판의 차례다
  - 업적이 없는 판(형식 10 까지)은 업적이 빈 것으로 읽는다
"""

from dataclasses import replace

from app.assets.schemas import AchievementDocument
from app.world.achievements import is_earned, newly_earned
from app.world.state import Holding, initial_state
from tests.assets import make_character

STAGES = [{'name': '낯섦', 'at': 0}, {'name': '친구', 'at': 30}, {'name': '연인', 'at': 70}]
WORLD = {
    'places': [
        {'id': 'library', 'name': '도서관', 'description': '', 'image_id': None},
        {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None},
    ],
    'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 10}],
    'start_place': 'library',
    'items': [{'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'image_id': None}],
    'start_items': [{'item': 'scarf', 'count': 1}],
    'affection': {'display': 'number', 'start': 10, 'stages': STAGES, 'rules': []},
}


def achievement(achievement_id: str, *items: dict, match: str = 'all') -> dict:
    return {'id': achievement_id, 'name': f'{achievement_id} 업적', 'when': {'match': match, 'items': list(items)}}


def condition(kind: str, target: str | None = None, value: str | None = None, count: int = 1) -> dict:
    return {'kind': kind, 'target': target, 'value': value, 'count': count}


ACHIEVEMENTS = [
    achievement('cafe', condition('visited_place', 'cafe')),
    achievement('scarves', condition('hold_item', 'scarf', count=2)),
    achievement('gift', condition('received_item', 'letter')),
    achievement('friend', condition('affection_stage', value='친구')),
    achievement('date', condition('scene_seen', 'first-date')),
    achievement('chatty', condition('messages_at_least', count=3)),
    achievement('either', condition('visited_place', 'cafe'), condition('messages_at_least', count=3), match='any'),
    achievement('empty'),
    achievement('unknown', condition('flies')),
]
DOCUMENT = make_character(world={**WORLD, 'achievements': ACHIEVEMENTS}).document
START = initial_state(DOCUMENT)


def ids(found) -> list[str]:
    return [one.id for one in found]


def test_nothing_is_met_at_the_start():
    assert newly_earned(DOCUMENT, START, 0, frozenset()) == ()


def test_each_kind_is_met_by_what_the_engine_knows():
    state = replace(
        START,
        visited=('library', 'cafe'),
        inventory=(Holding('scarf', 2),),
        received=('letter',),
        affection=30,
        shown=('first-date',),
    )

    assert ids(newly_earned(DOCUMENT, state, 3, frozenset())) == [
        'cafe',
        'scarves',
        'gift',
        'friend',
        'date',
        'chatty',
        'either',
    ]


def test_any_needs_one_and_all_needs_every_one():
    chatted = newly_earned(DOCUMENT, START, 3, frozenset())

    assert ids(chatted) == ['chatty', 'either']
    both = AchievementDocument.model_validate(
        achievement('both', condition('visited_place', 'cafe'), condition('messages_at_least', count=3))
    )
    assert is_earned(DOCUMENT, START, 3, both) is False


def test_owned_achievements_are_not_given_again():
    assert ids(newly_earned(DOCUMENT, START, 3, frozenset({'chatty'}))) == ['either']


def test_affection_below_the_stage_or_without_affection_is_not_met():
    friend = DOCUMENT.achievements[3]

    assert is_earned(DOCUMENT, replace(START, affection=29), 0, friend) is False
    assert is_earned(DOCUMENT, replace(START, affection=None), 0, friend) is False


def test_empty_and_unknown_conditions_are_never_met():
    assert is_earned(DOCUMENT, START, 99, DOCUMENT.achievements[7]) is False
    assert is_earned(DOCUMENT, START, 99, DOCUMENT.achievements[8]) is False


def test_a_version_without_achievements_has_none():
    assert make_character(world=WORLD).document.achievements == []
