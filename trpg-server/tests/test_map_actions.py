# trpg-server/tests/test_map_actions.py

"""
맵의 선언 행동: 가기(move)와 찾기(search).

다섯을 본다.
  - 가기: 아는 길로 이어진 곳으로 한 칸. 한쪽 길은 한쪽으로만. 받을 때 보고, 차례가 오면 다시 본다.
    간 곳은 서 본 곳이 되어 그곳의 안개 길이 보인다. 이벤트(character_moved)는 행동에 이어지고 행한 사람이 없다.
  - 받을 때의 거절: 이어지지 않은 곳, 모르는 곳, 숨긴 곳, 장소가 아닌 것이 같은 422 다. 맵 밖이면 409.
  - 찾기: 서 있는 곳의 숨긴 길마다 판의 판정을 굴린다. 찾으면 모두가 안다(맵, 이벤트).
  - 찾기가 드러내지 않는 것: 못 찾았을 때와 숨긴 길이 없을 때가 같다. 굴린 판정은 어디에도 없다.
    앞사람이 찾은 길은 다시 굴리지 않는다.
  - 맵 밖: 맵이 없는 판에서는 둘 다 할 수 없다.
"""

import json
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dice import ScriptedDice
from app.tables.models import TableInjury, TableSheet
from tests import test_table_map as map_tables
from tests.test_table_items import FRIEND, ME, events_of, read_table, table_url
from tests.test_table_map import known_places, known_routes, place_of, put_at, start_duo

pytestmark = pytest.mark.usefixtures('clean_tables')

# 지도 테스트의 픽스처를 그대로 쓴다. 방장(기사), 함께 앉는 사람(약사), 장소 여섯이 든 로어북.
# 맵: 성문(시작)-광장 큰길, 광장→지하실 숨긴 한쪽 길(지혜, 어려움), 성문-숲 안개 길, 오두막-숲 안개 길, 탑은 명소
me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore

# 지혜 10(보정 0)으로 어려움(20)을 넘는 눈과 못 넘는 눈
FOUND = 20
MISSED = 19


def load_dice(app: FastAPI, rolls: list[int]) -> ScriptedDice:
    """앱의 주사위를 정해진 눈을 내는 것으로 바꿔 꽂는다."""
    dice = ScriptedDice(rolls)
    app.state.dice = dice
    return dice


def going(place: dict) -> dict:
    return {'kind': 'move', 'place': place['id']}


SEARCHING = {'kind': 'search'}


async def declare(client: AsyncClient, headers: dict, table: dict, action: dict | None = None):
    """선언하는 요청. 응답을 그대로 돌려준다."""
    body = {'content': '움직인다.', 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


async def play(client: AsyncClient, me: dict, friend: dict, table: dict, narrated, mine=None, theirs=None) -> None:
    """둘 다 선언해 라운드를 닫고 서술이 끝나기를 기다린다. 행동을 붙이지 않으면 글만 낸다."""
    for headers, action in ((me, mine), (friend, theirs)):
        declared = await declare(client, headers, table, action)
        assert declared.status_code == status.HTTP_200_OK, declared.text
    await narrated()


async def outcome_of(client: AsyncClient, headers: dict, table: dict, number: int, user_id: uuid.UUID) -> dict:
    """그 라운드에서 그 사람의 선언의 결과."""
    response = await client.get(table_url(table, f'/rounds/{number}'), headers=headers)
    declaration = next(item for item in response.json()['declarations'] if item['user_id'] == str(user_id))
    return declaration['outcome']


def place_ref(entry: dict) -> dict:
    return {'entry_id': entry['id'], 'name': entry['name']}


# --- 가기 ---


async def test_a_character_goes_one_step_along_a_known_route(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore)

    await play(client, me, friend, table, narrated, mine=going(lore['square']))

    detail = await read_table(client, friend, table)
    assert (place_of(detail, ME), place_of(detail, FRIEND)) == (lore['square']['id'], lore['gate']['id'])
    assert (await outcome_of(client, friend, table, 1, ME))['move'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'from': place_ref(lore['gate']),
        'to': place_ref(lore['square']),
        'moved': True,
        'reason': None,
        # 이 길은 시간을 적지 않았다. 라운드의 걸음 안에서 간다
        'travel_minutes': None,
        'carry': None,
        # 자물쇠도 넘기 판정도 없는 길이다(#281)
        'unlocked': False,
        'cross': None,
        'effect': None,
    }
    # 판의 사건이 옮길 때와 같은 이벤트다. 행동에 이어지고, 행한 사람은 없다(엔진이 옮겼다)
    [moved] = await events_of(client, friend, table, 'character_moved')
    [acted] = [event for event in await events_of(client, me, table, 'player_action') if event['actor_id'] == str(ME)]
    assert (moved['actor_id'], moved['caused_by_sequence']) == (None, acted['sequence'])
    assert moved['payload'] == {
        'round': 1,
        'user_id': str(ME),
        'character_name': '기사',
        'from': place_ref(lore['gate']),
        'to': place_ref(lore['square']),
        'travel_minutes': None,
    }


async def test_going_into_the_fog_shows_what_lies_beyond(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore)

    # 성문의 안개 길로 숲에 간다. 숲에 서니 오두막으로 가는 안개 길이 보인다. 다음 라운드에 거기로 간다
    await play(client, me, friend, table, narrated, mine=going(lore['forest']))
    assert '오두막' in known_places(await read_table(client, me, table))
    await play(client, me, friend, table, narrated, mine=going(lore['hut']))

    assert place_of(await read_table(client, me, table), ME) == lore['hut']['id']


@pytest.mark.parametrize('where', ['tower', 'hut', 'cellar', 'potion', 'gate'])
async def test_only_a_place_next_door_can_be_reached(client: AsyncClient, me: dict, friend: dict, lore: dict, where):
    table = await start_duo(client, me, friend, lore)

    response = await declare(client, me, table, going(lore[where]))

    # 길 없는 명소, 아직 모르는 곳, 숨긴 곳, 장소가 아닌 것, 지금 서 있는 곳이 같은 답이다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'action.place 가 지금 장소에서 아는 길로 이어진 장소가 아닙니다.'}


async def test_a_one_way_route_goes_only_one_way(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await put_at(session, table, ME, lore['square'])
    load_dice(app, [FOUND])
    await play(client, me, friend, table, narrated, mine=SEARCHING)

    # 광장에서 지하실로는 내려간다. 지하실에서 광장으로는 올라오지 못한다(다른 길을 찾아야 한다)
    await play(client, me, friend, table, narrated, mine=going(lore['cellar']))
    assert place_of(await read_table(client, me, table), ME) == lore['cellar']['id']
    back = await declare(client, me, table, going(lore['square']))
    assert back.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_character_moved_away_meanwhile_does_not_go(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await declare(client, me, table, going(lore['square']))
    # 선언을 낸 뒤 탑에 서게 됐다(테스트가 옮긴다). 탑에서 광장으로 가는 길은 없다
    await put_at(session, table, ME, lore['tower'])

    await declare(client, friend, table)
    await narrated()

    assert place_of(await read_table(client, me, table), ME) == lore['tower']['id']
    outcome = (await outcome_of(client, me, table, 1, ME))['move']
    assert (outcome['moved'], outcome['reason'], outcome['from']['name']) == (False, 'not_adjacent', '탑')
    # 가지 못했으니 옮겨 간 이벤트가 없다
    assert await events_of(client, me, table, 'character_moved') == []


# --- 찾기 ---


async def test_searching_finds_a_hidden_route_for_everyone(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await put_at(session, table, ME, lore['square'])
    dice = load_dice(app, [FOUND])

    await play(client, me, friend, table, narrated, mine=SEARCHING)

    assert dice.remaining == 0
    found = {'from_place': place_ref(lore['square']), 'to_place': place_ref(lore['cellar']), 'two_way': False}
    assert (await outcome_of(client, friend, table, 1, ME)) == {
        'search': {'place': place_ref(lore['square']), 'found': [found], 'items': []}
    }
    [searched] = await events_of(client, friend, table, 'place_searched')
    assert searched['payload'] == {
        'round': 1,
        'character_name': '기사',
        'place': place_ref(lore['square']),
        'found': [found],
        'items': [],
    }
    # 찾은 길과 그 끝은 이제 모두가 안다. 방장도 이제야 안다
    for viewer in (me, friend):
        detail = await read_table(client, viewer, table)
        assert '지하실' in known_places(detail)
        assert ('square', 'cellar', False) in known_routes(detail, lore)


async def test_an_injury_hinders_the_search(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await put_at(session, table, ME, lore['square'])
    # 한쪽 눈을 잃었다(지혜의 판정에 -2). 다치지 않았으면 찾았을 눈이다
    sheet_id = await session.scalar(select(TableSheet.id).where(TableSheet.user_id == ME))
    session.add(
        TableInjury(
            table_id=uuid.UUID(table['id']), sheet_id=sheet_id, injury='lost_eye', source='injury_table', round_number=1
        )
    )
    await session.commit()
    load_dice(app, [FOUND])

    await play(client, me, friend, table, narrated, mine=SEARCHING)

    assert (await outcome_of(client, me, table, 1, ME))['search']['found'] == []


async def test_a_failed_search_looks_like_finding_nothing(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await put_at(session, table, ME, lore['square'])
    load_dice(app, [MISSED])

    await play(client, me, friend, table, narrated, mine=SEARCHING)

    # 숨긴 길이 있는데 못 찾았다. 결과에는 찾은 길이 없다는 것뿐이다. 굴린 눈도, 숨긴 길이 있었다는 것도 없다
    outcome = await outcome_of(client, me, table, 1, ME)
    assert outcome == {'search': {'place': place_ref(lore['square']), 'found': [], 'items': []}}
    round_ = (await client.get(table_url(table, '/rounds/1'), headers=me)).json()
    events = (await client.get(table_url(table, '/events'), params={'limit': 100}, headers=me)).json()
    for seen in (round_, events, await read_table(client, me, table)):
        assert lore['cellar']['id'] not in json.dumps(seen, ensure_ascii=False)
    assert not any(event['type'] == 'check_rolled' for event in events['items'])


async def test_searching_where_nothing_is_hidden_rolls_nothing(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore)
    # 눈을 하나도 적지 않았다. 굴리면 오류가 난다
    load_dice(app, [])

    await play(client, me, friend, table, narrated, mine=SEARCHING)

    searched = await outcome_of(client, me, table, 1, ME)
    assert searched == {'search': {'place': place_ref(lore['gate']), 'found': [], 'items': []}}


async def test_a_route_found_first_is_not_searched_again(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await put_at(session, table, ME, lore['square'])
    await put_at(session, table, FRIEND, lore['square'])
    # 앞사람(방장)이 찾았다. 뒷사람은 굴릴 길이 남지 않았다. 눈은 하나뿐이다
    dice = load_dice(app, [FOUND])

    await play(client, me, friend, table, narrated, mine=SEARCHING, theirs=SEARCHING)

    assert dice.remaining == 0
    assert len((await outcome_of(client, me, table, 1, ME))['search']['found']) == 1
    assert (await outcome_of(client, me, table, 1, FRIEND))['search']['found'] == []


async def test_a_found_route_stays_found(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await put_at(session, table, ME, lore['square'])
    load_dice(app, [FOUND])
    await play(client, me, friend, table, narrated, mine=SEARCHING)

    # 다시 찾아도 이미 찾은 길은 굴리지 않는다
    load_dice(app, [])
    await play(client, me, friend, table, narrated, mine=SEARCHING)

    assert (await outcome_of(client, me, table, 2, ME))['search']['found'] == []
    assert ('square', 'cellar', False) in known_routes(await read_table(client, me, table), lore)


# --- 맵 밖 ---


@pytest.mark.parametrize('action', [{'kind': 'search'}, 'move'])
async def test_a_table_without_a_map_cannot_move_or_search(
    client: AsyncClient, me: dict, friend: dict, lore: dict, action
):
    table = await start_duo(client, me, friend, lore, start_place=None)
    body = going(lore['gate']) if action == 'move' else action

    response = await declare(client, me, table, body)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_on_map'
