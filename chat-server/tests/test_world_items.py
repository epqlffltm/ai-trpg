# chat-server/tests/test_world_items.py

"""
물건을 쓰고 건네는 규칙(app/world/items.py, actions.py)과 "[지금]" 의 상대의 차림(scene.py). DB 도 모델도 쓰지 않는다.

보는 것.
  - 판에 없는 물건, 가지고 있지 않은 물건은 쓰거나 건넬 수 없다
  - 쓰기: 쓰면 없어지는 물건만 하나 준다. 0 이 되면 소지품에서 빠진다
  - 건네기: 하나 줄고, 옷이면 상대의 차림에 들어간다(한 번만). 옷이 아니면 차림은 그대로다
  - 행동 말의 글은 받침에 맞는 조사를 쓴다
  - 행동 하나는 kind 로 갈려 같은 규칙을 탄다
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.conversations.models import Conversation
from app.turns.service import action_messages
from app.world.actions import perform
from app.world.items import apply_give, apply_use, check_held, find_item, object_particle
from app.world.refusals import ActionRefusedError, Refusal
from app.world.scene import render_scene
from app.world.schemas import GiveAction, MoveAction, UseAction
from app.world.state import Holding, WorldState, initial_state
from tests.assets import make_character

ITEMS = [
    {'id': 'cookie', 'name': '쿠키', 'description': '', 'kind': 'thing', 'consumable': True, 'image_id': None},
    {'id': 'umbrella', 'name': '우산', 'description': '', 'kind': 'thing', 'consumable': False, 'image_id': None},
    {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'consumable': False, 'image_id': None},
    {'id': 'ring', 'name': '반지', 'description': '', 'kind': 'thing', 'consumable': False, 'image_id': None},
]
WORLD = {
    'places': [
        {'id': 'library', 'name': '도서관', 'description': '', 'image_id': None},
        {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None},
    ],
    'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 10}],
    'start_place': 'library',
    'items': ITEMS,
    'start_items': [{'item': 'cookie', 'count': 2}, {'item': 'umbrella', 'count': 1}, {'item': 'scarf', 'count': 2}],
}
DOCUMENT = make_character(world=WORLD).document
START = initial_state(DOCUMENT)


def item(item_id: str):
    return find_item(DOCUMENT, item_id)


@pytest.mark.parametrize(('item_id', 'reason'), [('sword', Refusal.ITEM_NOT_FOUND), ('ring', Refusal.NOT_HELD)])
def test_unknown_or_missing_items_are_refused(item_id: str, reason: Refusal):
    with pytest.raises(ActionRefusedError) as refused:
        check_held(DOCUMENT, START, item_id)

    assert refused.value.reason == reason


def test_using_a_consumable_takes_one_and_drops_the_line_at_zero():
    once = apply_use(START, item('cookie'))
    twice = apply_use(once, item('cookie'))

    assert once.inventory[0] == Holding('cookie', 1)
    assert [holding.item for holding in twice.inventory] == ['umbrella', 'scarf']
    with pytest.raises(ActionRefusedError):
        check_held(DOCUMENT, twice, 'cookie')


def test_using_a_lasting_item_keeps_it():
    assert apply_use(START, item('umbrella')) == START


def test_giving_clothing_puts_it_on_once():
    first = apply_give(START, item('scarf'))
    second = apply_give(first, item('scarf'))

    assert first.outfit == ('scarf',)
    assert (second.outfit, [holding.item for holding in second.inventory]) == (('scarf',), ['cookie', 'umbrella'])


def test_giving_other_things_only_takes_them():
    given = apply_give(START, item('umbrella'))

    assert (given.outfit, [holding.item for holding in given.inventory]) == ((), ['cookie', 'scarf'])


@pytest.mark.parametrize(('word', 'particle'), [('목도리', '를'), ('우산', '을'), ('쿠키', '를'), ('cake', '을(를)')])
def test_the_object_particle_follows_the_last_letter(word: str, particle: str):
    assert object_particle(word) == particle


def test_actions_are_told_apart_by_kind():
    used = perform(DOCUMENT, START, UseAction(kind='use', item='cookie'))
    given = perform(DOCUMENT, START, GiveAction(kind='give', item='scarf', words='추우니까'))
    moved = perform(DOCUMENT, START, MoveAction(kind='move', place='cafe'))

    assert (used.text, used.state.inventory[0]) == ('쿠키를 썼다.', Holding('cookie', 1))
    assert (given.text, given.state.outfit) == ('목도리를 건넸다.', ('scarf',))
    assert (moved.text, moved.state.place) == ('카페에 갔다. 10분이 걸렸다.', 'cafe')


def test_the_scene_shows_what_the_character_wears():
    worn = WorldState(place=None, minutes=0, inventory=(), visited=(), outfit=('scarf', 'lost'))

    assert render_scene(DOCUMENT, worn) == '[지금]\n상대의 차림: 목도리'


def test_words_after_an_action_come_later_than_the_action():
    conversation = Conversation(id=uuid.uuid4())
    now = datetime.now(UTC)

    action, words = action_messages(conversation, None, '목도리를 건넸다.', '받아.', now)

    # 가지의 끝을 생긴 차례로 고른다. 같은 때면 행동 말이 끝으로 뽑힐 수 있다
    assert (action.role, words.role, words.parent_id) == ('action', 'user', action.id)
    assert words.created_at > action.created_at
    assert len(action_messages(conversation, None, '쿠키를 썼다.', None, now)) == 1
