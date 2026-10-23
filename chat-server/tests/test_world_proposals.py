# chat-server/tests/test_world_proposals.py

"""
모델이 제안한 상태의 변화를 받아들이는 규칙(app/world/proposals.py, #676). DB 도 모델도 쓰지 않는다.

보는 것.
  - 할 수 있는 것(Offer): 호감도의 크기, 아직 받지 않은 줄 수 있는 물건, 길로 바로 이어진 곳
  - 선물: 소지품에 하나 더하고 받은 것으로 적는다. 줄 수 없는 것, 이미 받은 것, 모르는 것은 버린다
  - 이동: 사용자의 이동과 같다(시간, 가 본 곳, 호감도의 규칙). 이어지지 않은 곳과 지금 있는 곳은 버린다
  - 호감도: ±model_step 으로 자르고 0~100 안으로 자른다. 크기가 0 이거나 호감도가 없으면 버린다. 그대로면 칩이 없다
  - 단계로 보이는 캐릭터의 칩에는 크기를 싣지 않는다
  - 셋이 함께 오면 선물, 이동, 호감도의 차례다. 할 수 있는 것은 답을 쓰기 전의 상태로 정한다
"""

from dataclasses import replace

from app.conversation.changes import Proposed
from app.world.proposals import apply_proposals, offer_of, render_offer
from app.world.state import Holding, WorldState, initial_state
from tests.assets import make_character

WORLD = {
    'places': [
        {'id': 'library', 'name': '도서관', 'description': '', 'image_id': None},
        {'id': 'park', 'name': '공원', 'description': '', 'image_id': None},
        {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None},
        {'id': 'home', 'name': '집', 'description': '', 'image_id': None},
    ],
    'paths': [
        {'a': 'library', 'b': 'park', 'minutes': 15},
        {'a': 'cafe', 'b': 'library', 'minutes': 5},
        {'a': 'park', 'b': 'home', 'minutes': 30},
    ],
    'start_place': 'library',
    'items': [
        {'id': 'rose', 'name': '장미', 'description': '', 'kind': 'thing', 'giftable': True, 'image_id': None},
        {'id': 'stone', 'name': '돌', 'description': '', 'kind': 'thing', 'image_id': None},
        {'id': 'cake', 'name': '케이크', 'description': '', 'kind': 'thing', 'giftable': True, 'image_id': None},
    ],
    'start_items': [{'item': 'cake', 'count': 2}],
}
RULES = [{'id': 'walk', 'on': {'kind': 'reach_place', 'target': 'park'}, 'change': 10, 'once': True}]


def document(display: str = 'number', step: int = 3, start: int = 50, world: dict | None = None):
    affection = {
        'display': display,
        'start': start,
        'stages': [{'name': '보통', 'at': 0}],
        'rules': RULES,
        'model_step': step,
    }
    return make_character(world={**(world or WORLD), 'affection': affection}).document


def plain_document():
    return make_character(world=WORLD).document


def start(doc) -> WorldState:
    return initial_state(doc)


# --- 할 수 있는 것 ---


def test_the_offer_is_what_can_be_done_now():
    doc = document()

    offer = offer_of(doc, start(doc))

    assert offer.step == 3
    assert [item.id for item in offer.gifts] == ['rose', 'cake']
    assert [(route.place.id, route.minutes) for route in offer.routes] == [('park', 15), ('cafe', 5)]


def test_received_gifts_are_no_longer_offered():
    doc = document()

    offer = offer_of(doc, replace(start(doc), received=('rose',)))

    assert [item.id for item in offer.gifts] == ['cake']


def test_without_affection_or_a_map_less_is_offered():
    doc = plain_document()

    offer = offer_of(doc, replace(start(doc), place=None))

    assert (offer.step, offer.routes) == (0, ())


def test_only_real_distinct_neighbours_are_offered():
    paths = [
        {'a': 'library', 'b': 'park', 'minutes': 15},
        {'a': 'park', 'b': 'library', 'minutes': 99},
        {'a': 'library', 'b': 'library', 'minutes': 1},
        {'a': 'library', 'b': 'moon', 'minutes': 5},
    ]
    doc = document(world={**WORLD, 'paths': paths})

    offer = offer_of(doc, start(doc))

    assert [(route.place.id, route.minutes) for route in offer.routes] == [('park', 15)]


def test_the_offer_is_rendered_for_the_card():
    doc = document()

    text = render_offer(offer_of(doc, start(doc)))

    assert 'rose(장미), cake(케이크)' in text
    assert 'park(공원), cafe(카페)' in text
    assert 'stone' not in text


# --- 선물 ---


def test_a_gift_is_added_and_remembered():
    doc = document()

    applied = apply_proposals(doc, start(doc), Proposed(gift='cake'))

    assert applied.state.inventory == (Holding('cake', 3),)
    assert applied.state.received == ('cake',)
    assert applied.changes == ({'kind': 'gift', 'item': 'cake'},)


def test_a_new_gift_gets_a_new_line():
    doc = document()

    applied = apply_proposals(doc, start(doc), Proposed(gift='rose'))

    assert applied.state.inventory == (Holding('cake', 2), Holding('rose', 1))


def test_bad_gifts_are_dropped():
    doc = document()
    state = replace(start(doc), received=('rose',))

    for item in ('rose', 'stone', 'sword'):
        applied = apply_proposals(doc, state, Proposed(gift=item))
        assert (applied.state, applied.changes, applied.rejected) == (state, (), ('gift',))


# --- 이동 ---


def test_a_move_is_like_the_users_move():
    doc = document()

    applied = apply_proposals(doc, start(doc), Proposed(move='park'))

    assert (applied.state.place, applied.state.minutes, applied.state.visited) == ('park', 15, ('library', 'park'))
    # 호감도의 규칙(공원에 갔다)도 걸린다
    assert (applied.state.affection, applied.state.fired) == (60, ('walk',))
    assert applied.changes == ({'kind': 'move', 'place': 'park', 'minutes': 15},)


def test_a_path_written_the_other_way_works():
    doc = document()

    assert apply_proposals(doc, start(doc), Proposed(move='cafe')).state.place == 'cafe'


def test_bad_moves_are_dropped():
    doc = document()
    state = start(doc)

    for place in ('home', 'library', 'moon'):
        applied = apply_proposals(doc, state, Proposed(move=place))
        assert (applied.state, applied.changes, applied.rejected) == (state, (), ('move',))


# --- 호감도 ---


def test_affection_is_cut_to_the_step():
    doc = document(step=3)

    up = apply_proposals(doc, start(doc), Proposed(affection=50))
    down = apply_proposals(doc, start(doc), Proposed(affection=-2))

    assert (up.state.affection, up.changes) == (53, ({'kind': 'affection', 'rising': True, 'delta': 3},))
    assert (down.state.affection, down.changes) == (48, ({'kind': 'affection', 'rising': False, 'delta': -2},))


def test_affection_stays_within_bounds():
    doc = document(step=5, start=98)

    applied = apply_proposals(doc, start(doc), Proposed(affection=5))

    assert (applied.state.affection, applied.changes[0]['delta']) == (100, 2)


def test_no_change_is_no_chip():
    doc = document(start=100)

    applied = apply_proposals(doc, start(doc), Proposed(affection=1))

    assert (applied.state.affection, applied.changes, applied.rejected) == (100, (), ())


def test_zero_step_or_no_affection_drops_it():
    for doc in (document(step=0), plain_document()):
        applied = apply_proposals(doc, start(doc), Proposed(affection=2))
        assert (applied.changes, applied.rejected) == ((), ('affection',))


def test_a_stage_character_does_not_show_the_size():
    doc = document(display='stage')

    applied = apply_proposals(doc, start(doc), Proposed(affection=2))

    assert applied.changes == ({'kind': 'affection', 'rising': True, 'delta': None},)


# --- 함께 ---


def test_all_three_apply_in_order():
    doc = document()

    applied = apply_proposals(doc, start(doc), Proposed(affection=-3, gift='rose', move='park'))

    assert [change['kind'] for change in applied.changes] == ['gift', 'move', 'affection']
    # 이동의 규칙(+10) 뒤에 모델의 변화(-3)다. 칩에는 모델의 변화만 있다
    assert applied.state.affection == 57
    assert applied.changes[-1]['delta'] == -3


def test_nothing_proposed_changes_nothing():
    doc = document()
    state = start(doc)

    assert apply_proposals(doc, state, Proposed()).state == state
