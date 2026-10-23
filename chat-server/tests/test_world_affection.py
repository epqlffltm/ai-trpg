# chat-server/tests/test_world_affection.py

"""
호감도의 규칙(app/world/affection.py)과 상태, 장면, 응답의 모양. DB 도 모델도 쓰지 않는다.

보는 것.
  - 시작 값은 판의 것이다. 판에 호감도가 없으면 없다. 호감도가 없던 상태는 시작 값으로 채운다
  - 행동의 (종류, 대상)이 같은 규칙이 모두 걸리고, 0~100 안으로 자른다. 다른 행동에는 걸리지 않는다
  - 처음 한 번만인 규칙은 그 가지에서 한 번만 걸린다
  - 단계는 값이 경계 이상인 마지막 단계다. 모델에는 단계 이름만 간다
  - 단계로 보이는 캐릭터는 숫자를 내려보내지 않는다
  - 이동, 쓰기, 건네기가 각자의 행동으로 규칙을 건다
"""

import pytest

from app.world.actions import perform
from app.world.affection import apply_affection, stage_index
from app.world.scene import render_scene
from app.world.schemas import GiveAction, MoveAction, UseAction, affection_out
from app.world.state import WorldState, filled, initial_state
from tests.assets import make_character

# 대화의 시작 시각(몇 시)
NOON = 12

STAGES = [{'name': '낯섦', 'at': 0}, {'name': '친구', 'at': 30}, {'name': '연인', 'at': 70}]
RULES = [
    {'id': 'gift', 'on': {'kind': 'give_item', 'target': 'scarf'}, 'change': 15, 'once': False},
    {'id': 'gift-first', 'on': {'kind': 'give_item', 'target': 'scarf'}, 'change': 10, 'once': True},
    {'id': 'date', 'on': {'kind': 'reach_place', 'target': 'cafe'}, 'change': 20, 'once': True},
    {'id': 'rude', 'on': {'kind': 'use_item', 'target': 'cookie'}, 'change': -20, 'once': False},
]
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
    'start_items': [{'item': 'scarf', 'count': 3}, {'item': 'cookie', 'count': 2}],
}


def document(display: str = 'number', start: int = 10):
    affection = {'display': display, 'start': start, 'stages': STAGES, 'rules': RULES}
    return make_character(world={**WORLD, 'affection': affection}).document


DOCUMENT = document()
START = initial_state(DOCUMENT)


def test_the_start_value_comes_from_the_version():
    assert START.affection == 10
    assert initial_state(make_character(world=WORLD).document).affection is None


def test_a_state_written_before_affection_is_filled_with_the_start():
    old = WorldState(place='cafe', minutes=5, inventory=(), visited=('cafe',))

    assert filled(DOCUMENT, old).affection == 10
    assert filled(DOCUMENT, START) == START
    assert filled(make_character(world=WORLD).document, old) == old


def test_all_matching_rules_apply_and_first_time_rules_only_once():
    once = apply_affection(DOCUMENT, START, 'give_item', 'scarf')
    twice = apply_affection(DOCUMENT, once, 'give_item', 'scarf')

    assert (once.affection, once.fired) == (35, ('gift-first',))
    assert (twice.affection, twice.fired) == (50, ('gift-first',))


def test_values_stay_between_zero_and_a_hundred():
    low = apply_affection(DOCUMENT, START, 'use_item', 'cookie')
    high = apply_affection(document(start=95), initial_state(document(start=95)), 'reach_place', 'cafe')

    assert (low.affection, high.affection) == (0, 100)


@pytest.mark.parametrize(
    ('kind', 'target'), [('give_item', 'cookie'), ('reach_place', 'library'), ('use_item', 'scarf')]
)
def test_other_actions_change_nothing(kind: str, target: str):
    assert apply_affection(DOCUMENT, START, kind, target) == START


def test_without_affection_nothing_changes():
    plain = make_character(world=WORLD).document
    state = initial_state(plain)

    assert apply_affection(plain, state, 'give_item', 'scarf') == state


@pytest.mark.parametrize(('value', 'index'), [(0, 0), (29, 0), (30, 1), (69, 1), (70, 2), (100, 2)])
def test_the_stage_is_the_last_one_reached(value: int, index: int):
    assert stage_index(DOCUMENT.affection, value) == index


def test_the_model_sees_only_the_stage_name():
    scene = render_scene(DOCUMENT, apply_affection(DOCUMENT, START, 'give_item', 'scarf'), NOON)

    assert '사용자에 대한 호감: 친구' in scene
    assert '35' not in scene


def test_a_stage_display_does_not_send_the_number():
    staged = document(display='stage')

    shown = affection_out(DOCUMENT, START)
    hidden = affection_out(staged, initial_state(staged))

    assert shown.model_dump() == {'display': 'number', 'value': 10, 'stage': '낯섦', 'stage_index': 0, 'stages': 3}
    assert (hidden.value, hidden.stage) == (None, '낯섦')
    assert affection_out(make_character(world=WORLD).document, START) is None


def test_each_action_triggers_its_own_rules():
    moved = perform(DOCUMENT, START, MoveAction(kind='move', place='cafe'), NOON)
    used = perform(DOCUMENT, START, UseAction(kind='use', item='cookie'), NOON)
    given = perform(DOCUMENT, START, GiveAction(kind='give', item='scarf'), NOON)

    assert (moved.state.affection, used.state.affection, given.state.affection) == (30, 0, 35)
