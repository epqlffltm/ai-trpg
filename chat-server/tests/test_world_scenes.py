# chat-server/tests/test_world_event_scenes.py

"""
이벤트 씬의 조건을 맞추는 엔진(app/world/scenes.py, #669)을 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 장소에 갔다: 그 장소로 이동할 때만 맞는다. 다른 곳으로 가거나 다른 행동이면 맞지 않는다
  - 물건을 처음 건넸다: 그 물건을 건널 때만 맞는다. 같은 물건을 써도 맞지 않는다
  - 호감도 단계: 행동 뒤의 값이 그 단계 이상이면 맞는다. 호감도가 없거나 모르는 단계면 맞지 않는다
  - 한 가지에서 한 번만 나온다. 나온 것은 상태에 적힌다
  - 한 행동에 여럿이면 판의 차례로 첫 것이 답에 붙고 모두 나온 것으로 적힌다. 연 것으로 세는 것은 해금 대상뿐이다
  - 모르는 조건의 종류는 맞지 않는다
  - 모델에는 "[지금]" 에 그 장면이 간다(설명이 없으면 제목)
"""

import uuid
from dataclasses import replace

from app.assets.schemas import CharacterDocument, EventSceneDocument
from app.world.actions import perform
from app.world.scene import render_scene
from app.world.scenes import Event, Revealed, find_scene, reveal
from app.world.schemas import GiveAction, MoveAction, UseAction, WaitAction
from app.world.state import initial_state
from tests.assets import make_character

NOON = 12
PICTURE = str(uuid.UUID(int=5))


def event_scene(scene_id: str, kind: str, target: str, **fields) -> dict:
    return {
        'id': scene_id,
        'title': scene_id,
        'image_id': PICTURE,
        'description': f'{scene_id} 의 장면',
        'collectible': True,
        'when': {'kind': kind, 'target': target},
        **fields,
    }


WORLD = {
    'places': [
        {'id': 'library', 'name': '도서관', 'description': '', 'image_id': None},
        {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None},
    ],
    'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 10}],
    'start_place': 'library',
    'items': [
        {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'image_id': None},
        {'id': 'cookie', 'name': '쿠키', 'description': '', 'kind': 'thing', 'consumable': True, 'image_id': None},
    ],
    'start_items': [{'item': 'scarf', 'count': 2}, {'item': 'cookie', 'count': 2}],
    'affection': {
        'display': 'number',
        'start': 20,
        'stages': [{'name': '낯섦', 'at': 0}, {'name': '친구', 'at': 30}],
        'rules': [{'id': 'gift', 'on': {'kind': 'give_item', 'target': 'scarf'}, 'change': 15, 'once': False}],
    },
    'event_scenes': [
        event_scene('date', 'reach_place', 'cafe'),
        event_scene('gift', 'give_item', 'scarf', collectible=False),
        event_scene('friend', 'affection_stage', '친구', description=''),
    ],
}
DOCUMENT: CharacterDocument = make_character(world=WORLD).document
START = initial_state(DOCUMENT)


def ids(revealed: Revealed) -> list[str]:
    return [item.id for item in revealed.event_scenes]


# --- 조건 ---


def test_reaching_the_place_shows_it():
    performed = perform(DOCUMENT, START, MoveAction(kind='move', place='cafe'), NOON)

    assert ids(performed.revealed) == ['date']
    assert performed.state.shown == ('date',)


def test_another_action_does_not_count_as_reaching():
    used = perform(DOCUMENT, START, UseAction(kind='use', item='cookie'), NOON)
    waited = perform(DOCUMENT, START, WaitAction(kind='wait'), NOON)

    assert (ids(used.revealed), ids(waited.revealed)) == ([], [])


def test_giving_the_item_shows_it_and_using_it_does_not():
    used = perform(DOCUMENT, START, UseAction(kind='use', item='scarf'), NOON)
    given = perform(DOCUMENT, START, GiveAction(kind='give', item='cookie'), NOON)

    assert (ids(used.revealed), ids(given.revealed)) == ([], [])


def test_reaching_an_affection_stage_shows_it():
    # 목도리를 건네면 20 + 15 = 35 로 친구가 된다. 같은 행동으로 건넨 것도 맞는다
    performed = perform(DOCUMENT, START, GiveAction(kind='give', item='scarf'), NOON)

    assert performed.state.affection == 35
    assert ids(performed.revealed) == ['gift', 'friend']
    assert performed.revealed.shown.id == 'gift'
    # 건넨 이벤트 씬은 해금 대상이 아니라 연 것으로 세지 않는다
    assert performed.revealed.collected == ('friend',)
    assert performed.state.shown == ('gift', 'friend')


def test_a_stage_already_reached_shows_on_the_next_action():
    friendly = replace(START, affection=40)

    assert ids(reveal(DOCUMENT, friendly, None)) == ['friend']


def test_each_shows_once_on_a_branch():
    moved = perform(DOCUMENT, START, MoveAction(kind='move', place='cafe'), NOON)
    back = perform(DOCUMENT, moved.state, MoveAction(kind='move', place='library'), NOON)
    again = perform(DOCUMENT, back.state, MoveAction(kind='move', place='cafe'), NOON)

    assert (ids(back.revealed), ids(again.revealed)) == ([], [])
    assert again.state.shown == ('date',)


def test_without_affection_or_with_an_unknown_stage_nothing_shows():
    loveless = make_character(world={**WORLD, 'affection': None}).document
    odd = make_character(world={**WORLD, 'event_scenes': [event_scene('love', 'affection_stage', '연인')]}).document
    rich = replace(initial_state(odd), affection=100)

    assert ids(reveal(loveless, initial_state(loveless), None)) == []
    assert ids(reveal(odd, rich, None)) == []


def test_an_unknown_kind_never_matches():
    odd = make_character(world={**WORLD, 'event_scenes': [event_scene('talk', 'say_word', 'cafe')]}).document

    assert ids(reveal(odd, initial_state(odd), Event('say_word', 'cafe'))) == []


def test_event_scenes_are_found_by_id():
    assert find_scene(DOCUMENT, 'date').title == 'date'
    assert (find_scene(DOCUMENT, 'gone'), find_scene(DOCUMENT, None)) == (None, None)


# --- 모델에 가는 것 ---


def test_the_scene_goes_to_the_model():
    date: EventSceneDocument = find_scene(DOCUMENT, 'date')
    friend: EventSceneDocument = find_scene(DOCUMENT, 'friend')

    assert render_scene(DOCUMENT, START, NOON, date).endswith('\n장면: date 의 장면')
    # 설명이 없으면 제목이다
    assert render_scene(DOCUMENT, START, NOON, friend).endswith('\n장면: friend')
    assert '장면:' not in render_scene(DOCUMENT, START, NOON)
