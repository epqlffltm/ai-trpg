# chat-server/tests/test_world_rules.py

"""
장소와 소지품의 규칙(app/world/state.py, moves.py, scene.py)과 행동 말을 모델에 보내는 모양(app/turns/prompt.py).
DB 도 모델도 쓰지 않는다.

보는 것.
  - 시작 상태는 판의 처음 있는 장소와 시작 소지품이다. 지도가 없으면 장소가 없다
  - 지금의 상태는 가지의 끝에서 거슬러 올라가 처음 만나는 상태다
  - 이동: 지도가 없음, 모르는 곳, 이미 그곳, 길이 없음은 갈 수 없다. 길은 양쪽으로 다닌다.
    가면 시간이 흐르고 처음 간 곳만 가 본 곳에 더한다
  - "[지금]" 블록: 장소와 설명, 갈 수 있는 곳(양쪽 길), 소지품. 적을 것이 없으면 블록이 없다
  - 행동 말은 [행동] 을 붙여 사람의 차례로 간다. 카드에서 [지금] 은 시작 상황 뒤, 다음 답 추천의 지시 앞이다
"""

import uuid

import pytest
from ai_core.provider import Role

from app.assets.schemas import CharacterDocument
from app.conversation.window import Turn
from app.turns.prompt import CharacterCard, build_messages, render_card
from app.world.moves import MoveRefusal, MoveRefusedError, apply_move, check_move, move_text, path_minutes
from app.world.scene import render_scene
from app.world.state import Holding, WorldState, initial_state, state_at
from tests.assets import make_character

WORLD = {
    'places': [
        {'id': 'library', 'name': '도서관', 'description': '책 냄새가 난다.', 'image_id': None},
        {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None},
        {'id': 'roof', 'name': '옥상', 'description': '', 'image_id': None},
    ],
    'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 15}, {'a': 'roof', 'b': 'library', 'minutes': 0}],
    'start_place': 'library',
    'items': [{'id': 'book', 'name': '시집', 'description': '', 'kind': 'thing', 'image_id': None}],
    'start_items': [{'item': 'book', 'count': 2}],
}
DOCUMENT = make_character(world=WORLD).document
PLAIN = make_character().document
START = initial_state(DOCUMENT)


def test_the_start_comes_from_the_version():
    assert WorldState(place='library', minutes=0, inventory=(Holding('book', 2),), visited=('library',)) == START
    assert initial_state(PLAIN) == WorldState(place=None, minutes=0, inventory=(), visited=())


def test_the_state_is_the_nearest_one_up_the_branch():
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    moved = apply_move(START, 'cafe', 15)

    assert state_at([first, second, third], {second: moved}, START) == moved
    assert state_at([first, second, third], {first: START, second: moved}, START) == moved
    assert state_at([first, second, third], {}, START) == START
    assert state_at([first, second], {third: moved}, START) == START


@pytest.mark.parametrize(
    ('document', 'state', 'target', 'reason'),
    [
        (PLAIN, initial_state(PLAIN), 'cafe', MoveRefusal.NO_MAP),
        (DOCUMENT, START, 'garden', MoveRefusal.PLACE_NOT_FOUND),
        (DOCUMENT, START, 'library', MoveRefusal.ALREADY_THERE),
        (DOCUMENT, apply_move(START, 'cafe', 15), 'roof', MoveRefusal.NOT_CONNECTED),
    ],
)
def test_places_that_cannot_be_reached_are_refused(
    document: CharacterDocument, state: WorldState, target: str, reason: MoveRefusal
):
    with pytest.raises(MoveRefusedError) as refused:
        check_move(document, state, target)

    assert refused.value.reason == reason


def test_paths_go_both_ways():
    assert path_minutes(DOCUMENT, 'cafe', 'library') == path_minutes(DOCUMENT, 'library', 'cafe') == 15
    assert path_minutes(DOCUMENT, 'cafe', 'roof') is None
    assert check_move(DOCUMENT, START, 'roof') == 0


def test_moving_passes_time_and_remembers_new_places_once():
    there = apply_move(START, 'cafe', check_move(DOCUMENT, START, 'cafe'))
    back = apply_move(there, 'library', 15)

    assert (there.place, there.minutes, there.visited) == ('cafe', 15, ('library', 'cafe'))
    assert (back.place, back.minutes, back.visited) == ('library', 30, ('library', 'cafe'))
    assert back.inventory == START.inventory


def test_the_move_is_written_for_people_and_the_model():
    assert move_text(DOCUMENT, 'cafe', 15) == '카페에 갔다. 15분이 걸렸다.'
    assert move_text(DOCUMENT, 'roof', 0) == '옥상에 갔다.'


def test_the_scene_has_the_place_the_exits_and_the_belongings():
    assert render_scene(DOCUMENT, START) == '\n'.join(
        [
            '[지금]',
            '장소: 도서관 — 책 냄새가 난다.',
            '갈 수 있는 곳: 카페(15분), 옥상(0분)',
            '사용자의 소지품: 시집 2개',
        ]
    )
    at_cafe = apply_move(START, 'cafe', 15)
    assert render_scene(DOCUMENT, at_cafe).split('\n')[1:3] == ['장소: 카페', '갈 수 있는 곳: 도서관(15분)']


def test_unknown_items_are_left_out_and_nothing_is_no_scene():
    stray = WorldState(place=None, minutes=0, inventory=(Holding('ring', 1),), visited=())

    assert render_scene(DOCUMENT, stray) is None
    assert render_scene(PLAIN, initial_state(PLAIN)) is None


def test_an_action_goes_to_the_model_as_the_users_turn_with_a_mark():
    messages = build_messages('카드', [Turn('action', '카페에 갔다.'), Turn('user', '안녕')])

    assert [(message.role, message.content) for message in messages[1:]] == [
        (Role.USER, '[행동] 카페에 갔다.'),
        (Role.USER, '안녕'),
    ]


def test_the_scene_sits_between_the_start_and_the_suggestions():
    card = render_card(
        CharacterCard(name='세라', intro_html='', speech_examples='', age='', gender=''),
        None,
        '비가 온다.',
        suggest=True,
        scene='[지금]\n장소: 카페',
    )

    sections = [section.split('\n')[0] for section in card.split('\n\n')]
    assert sections[-3:] == ['[시작 상황]', '[지금]', '[다음 답 추천]']
