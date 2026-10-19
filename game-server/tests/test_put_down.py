# game-server/tests/test_put_down.py

"""
가진 물건을 내려놓는 행동(put_down, #454)을 검증한다.

맵과 판은 test_quest_goals.py 의 것이다. 성문(시작)과 숲이 열린 길로 이어진다.
물건은 치유 물약과 늑대 가죽이다. 소지품은 방장의 주기로 채운다.

보는 것.
  - 내려놓기: 가진 것에서 빠지고 그 장소에 보이게 놓인다. 결과와 item_put_down 이벤트가 남는다.
    같은 물건이 놓여 있으면 거기에 더한다. 다음 라운드에 다른 사람이 줍는다.
  - 받기: 맵에 서 있고, 판의 물건을 그만큼 가지고 있어야 한다.
  - 차례: 차례가 왔을 때 그만큼 없으면 놓지 않는다(not_held).
  - 표: 같은 장소의 같은 물건의 보이는 줄에 더하고, 없으면 판의 줄 뒤에 새 줄을 만든다. 숨긴 줄에는 더하지 않는다.
  - 서술: 한 일의 줄에 내려놓기의 결과가 붙는다. 놓은 물건이 그 장소의 놓인 물건에 보인다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.rounds.move_lines import describe_put_down
from app.rounds.narrator import ItemNote, PutDownNote
from app.tables import place_items
from app.tables.models import GameTable, TablePlaceItem
from tests.test_place_items import declare_raw, items_at, lying, outcome, take
from tests.test_quest_goals import declare, make_world, start
from tests.test_table_items import FRIEND, ME, bearer, events_of, give, read_table
from tests.test_table_items import held as held_items
from tests.test_table_items import take as take_away
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

PUT = '물약을 내려놓는다.'


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


def put_down(world: dict, item: str, count: int = 1) -> dict:
    return {'kind': 'put_down', 'item': world[item]['id'], 'count': count}


async def stock(client: AsyncClient, me: dict, table: dict, world: dict, item: str, count: int) -> None:
    """방장이 나(기사)에게 물건을 준다."""
    given = await give(client, me, table, ME, world[item], count)
    assert given.status_code == status.HTTP_200_OK, given.text


# --- 내려놓기 ---


async def test_putting_down_leaves_it_in_sight(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [])
    await stock(client, me, table, world, 'potion', 3)

    await declare(client, me, table, PUT, put_down(world, 'potion', 2))
    await narrated()

    seen = await read_table(client, me, table)
    assert held_items(seen, ME) == [('치유 물약', 1)]
    assert items_at(seen, world, 'gate') == [('치유 물약', 2)]
    assert (await outcome(client, me, table, 1))['put_down'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'place': {'entry_id': world['gate']['id'], 'name': '성문'},
        'entry_id': world['potion']['id'],
        'name': '치유 물약',
        'count': 2,
        'put': True,
        'reason': None,
        'remaining': 1,
    }
    (put,) = await events_of(client, me, table, 'item_put_down')
    (acted,) = await events_of(client, me, table, 'player_action')
    assert put['actor_id'] is None
    assert put['caused_by_sequence'] == acted['sequence']
    # 누가 했는지는 행동의 이벤트에 있다. 결과에는 user_id 를 싣지 않는다
    assert put['payload'] == {
        'round': 1,
        'character_name': '기사',
        'place': {'entry_id': world['gate']['id'], 'name': '성문'},
        'entry_id': world['potion']['id'],
        'name': '치유 물약',
        'count': 2,
        'put': True,
        'reason': None,
        'remaining': 1,
    }


async def test_putting_down_all_empties_the_bag(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [])
    await stock(client, me, table, world, 'potion', 2)

    await declare(client, me, table, PUT, put_down(world, 'potion', 2))
    await narrated()

    seen = await read_table(client, me, table)
    assert held_items(seen, ME) == []
    assert (await outcome(client, me, table, 1))['put_down']['remaining'] == 0


async def test_putting_down_joins_what_already_lies_there(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [], place_items=[lying(world, 'gate', 'potion')])
    await stock(client, me, table, world, 'potion', 2)

    await declare(client, me, table, PUT, put_down(world, 'potion', 2))
    await narrated()

    assert items_at(await read_table(client, me, table), world, 'gate') == [('치유 물약', 3)]


async def test_someone_picks_it_up_the_next_round(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    world = await make_world(client, me)
    table = await start(client, me, world, [], friend)
    await stock(client, me, table, world, 'potion', 1)

    await declare(client, me, table, PUT, put_down(world, 'potion'))
    await declare(client, friend, table)
    await narrated()
    await declare(client, me, table)
    await declare(client, friend, table, '물약을 줍는다.', take(world, 'potion'))
    await narrated()

    seen = await read_table(client, me, table)
    assert (held_items(seen, ME), held_items(seen, FRIEND)) == ([], [('치유 물약', 1)])
    assert items_at(seen, world, 'gate') == []


async def test_what_is_put_down_this_round_cannot_be_taken_yet(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    world = await make_world(client, me)
    table = await start(client, me, world, [], friend)
    await stock(client, me, table, world, 'potion', 1)
    await declare(client, me, table, PUT, put_down(world, 'potion'))

    response = await declare_raw(client, friend, table, take(world, 'potion'))

    # 줍기는 받을 때 그 자리에 보이는 것만 받는다. 아직 기사의 손에 있다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'item' in response.text


# --- 받기 ---


@pytest.mark.parametrize(('held', 'count'), [(0, 1), (1, 2)])
async def test_only_what_is_held_can_be_put_down(client: AsyncClient, me: dict[str, str], held: int, count: int):
    world = await make_world(client, me)
    table = await start(client, me, world, [])
    if held:
        await stock(client, me, table, world, 'potion', held)

    response = await declare_raw(client, me, table, put_down(world, 'potion', count))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'item_not_held' in response.text


async def test_an_item_not_in_the_rules_cannot_be_put_down(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    table = await start(client, me, world, [])

    response = await declare_raw(client, me, table, {'kind': 'put_down', 'item': str(uuid.uuid4())})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'item' in response.text


async def test_off_the_map_nothing_can_be_put_down(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    table = await start(client, me, world, [], start_place=None, routes=[], encounters=[])
    await stock(client, me, table, world, 'potion', 1)

    response = await declare_raw(client, me, table, put_down(world, 'potion'))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_on_map'


@pytest.mark.parametrize('count', [0, 100])
async def test_the_count_must_be_sensible(client: AsyncClient, me: dict[str, str], count: int):
    world = await make_world(client, me)
    table = await start(client, me, world, [])

    response = await declare_raw(client, me, table, put_down(world, 'potion', count))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 차례 ---


async def test_what_is_gone_by_the_turn_is_not_put_down(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    world = await make_world(client, me)
    table = await start(client, me, world, [], friend)
    await stock(client, me, table, world, 'potion', 1)
    await declare(client, me, table, PUT, put_down(world, 'potion'))
    # 받은 뒤 차례가 오기 전에 물건이 없어졌다
    taken = await take_away(client, me, table, ME, world['potion'])
    assert taken.status_code == status.HTTP_200_OK, taken.text

    await declare(client, friend, table)
    await narrated()

    put = (await outcome(client, me, table, 1))['put_down']
    assert (put['put'], put['reason'], put['remaining']) == (False, 'not_held', 0)
    assert items_at(await read_table(client, me, table), world, 'gate') == []
    (event,) = await events_of(client, me, table, 'item_put_down')
    assert (event['payload']['put'], event['payload']['reason']) == (False, 'not_held')


# --- 표 ---


def a_table(*rows: TablePlaceItem) -> GameTable:
    table = GameTable(id=uuid.uuid4())
    table.place_items = list(rows)
    return table


def row(slot: int, place: uuid.UUID, entry: uuid.UUID, count: int, hidden_row: bool = False) -> TablePlaceItem:
    return TablePlaceItem(slot=slot, place_id=place, entry_id=entry, count=count, hidden=hidden_row)


PLACE, OTHER, ROPE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def test_put_down_adds_to_the_visible_row_of_that_thing():
    table = a_table(row(0, PLACE, ROPE, 0), row(1, PLACE, ROPE, 2))

    place_items.put_down(table, PLACE, ROPE, 3)

    # 다 가져가 0 이 된 줄도 보이는 줄이다. 줄 순서로 처음 것에 더한다
    assert [(item.slot, item.count) for item in table.place_items] == [(0, 3), (1, 2)]


def test_put_down_makes_a_new_row_after_the_rest():
    table = a_table(row(0, PLACE, ROPE, 1, hidden_row=True), row(3, OTHER, ROPE, 1))

    place_items.put_down(table, PLACE, ROPE, 2)

    # 숨긴 줄에 더하면 찾기 전에 보이게 된다. 다른 장소의 줄도 아니다
    (added,) = table.place_items[2:]
    assert (added.slot, added.place_id, added.entry_id, added.count, added.hidden) == (4, PLACE, ROPE, 2, False)
    assert added.table_id == table.id


def test_put_down_on_an_empty_table_starts_at_zero():
    table = a_table()

    place_items.put_down(table, PLACE, ROPE, 1)

    assert [(item.slot, item.count) for item in table.place_items] == [(0, 1)]


# --- 서술 ---


async def test_the_narrator_sees_what_was_put_down(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    world = await make_world(client, me)
    table = await start(client, me, world, [])
    await stock(client, me, table, world, 'potion', 2)

    await declare(client, me, table, PUT, put_down(world, 'potion'))
    await narrated()

    (request,) = narrator.requests
    (moved,) = request.moves
    assert moved.put_down == PutDownNote(name='치유 물약', count=1, put=True)
    assert moved.items == [ItemNote(name='치유 물약', count=1)]
    assert moved.place.items == [ItemNote(name='치유 물약', count=1)]


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (PutDownNote(name='밧줄', count=1, put=True), '(내려놓기: 밧줄 1개를 내려놓았다)'),
        (PutDownNote(name='밧줄', count=2, put=False), '(내려놓기: 밧줄 2개를 가지고 있지 않았다)'),
    ],
)
def test_the_put_down_line(note: PutDownNote, line: str):
    assert describe_put_down(note) == line
