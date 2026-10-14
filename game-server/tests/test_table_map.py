# game-server/tests/test_table_map.py

"""
테이블의 맵: 캐릭터가 서 있는 곳과, 테이블이 아는 맵.

다섯을 본다.
  - 시작: 캐릭터 모두가 시작 장소에 선다. 시작 장소는 서 본 곳이 된다.
  - 아는 것: 열린 길과 명소는 처음부터, 안개 길은 한쪽 끝에 서 본 뒤부터. 아는 길의 끝은 아는 장소다.
    숨긴 길과 숨긴 길로만 닿는 장소는 방장에게도 나가지 않는다. 모두가 같은 맵을 본다.
  - 방장이 옮기기: 진행 중에, 살아 있는 캐릭터를, 아는 장소로만. 이벤트로 남는다. 같은 곳이면 아무 일도 없다.
  - 새 캐릭터: 앞 캐릭터가 쓰러진 곳에서 들어온다. 들어온 이벤트에 그 장소가 적힌다.
  - 맵이 없는 판: 맵도 위치도 없고, 옮길 곳도 없다.
"""

import json
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.sheets import SHEET
from tests.test_table_items import (
    FRIEND,
    LOREBOOKS_URL,
    ME,
    NO_SUCH_ID,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    STRANGER,
    TABLES_URL,
    bearer,
    events_of,
    kill,
    post,
    read_table,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    """방장의 머리말. 직접 만든 캐릭터(기사)를 한다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    """함께 앉는 사람의 머리말. 직접 만든 캐릭터(약사)를 한다."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """장소 여섯(성문, 광장, 지하실, 숲, 오두막, 탑)과 물건 하나가 든 로어북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='성의 장소들')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind=kind)

    return {
        'lorebook': lorebook,
        'gate': await entry('성문', 'place'),
        'square': await entry('광장', 'place'),
        'cellar': await entry('지하실', 'place'),
        'forest': await entry('숲', 'place'),
        'hut': await entry('오두막', 'place'),
        'tower': await entry('탑', 'place'),
        'potion': await entry('치유 물약', 'item'),
    }


def route(start: dict, end: dict, **fields) -> dict:
    return {'from_place': start['id'], 'to_place': end['id'], **fields}


def the_map(lore: dict) -> dict:
    """
    성문에서 시작한다. 성문-광장은 큰길(열림), 광장에서 지하실로는 숨긴 한쪽 길,
    성문-숲은 안개 길, 오두막-숲도 안개 길이다(숲 쪽에서도 보인다). 탑은 명소다(가는 길은 없다).
    """
    return {
        'start_place': lore['gate']['id'],
        'routes': [
            route(lore['gate'], lore['square']),
            route(
                lore['square'],
                lore['cellar'],
                two_way=False,
                visibility='hidden',
                find={'ability': 'wis', 'difficulty': 'hard'},
            ),
            route(lore['gate'], lore['forest'], visibility='fog'),
            route(lore['hut'], lore['forest'], visibility='fog'),
        ],
        'landmarks': [lore['tower']['id']],
    }


async def open_duo(client: AsyncClient, me: dict, friend: dict, lore: dict, **scenario) -> dict:
    """둘이 앉은 테이블. 시작하지 않았다. 판의 맵은 받은 대로다(기본은 맵 없음)."""
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': SHEET,
        'lorebook_ids': [lore['lorebook']['id']],
        **scenario,
    }
    made = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{made["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=made['id'], version=1, capacity=2)
    joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    assert joined.status_code == status.HTTP_200_OK, joined.text
    await client.put(table_url(table, '/character'), json={'name': '기사'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '약사'}, headers=friend)
    return table


async def start_duo(client: AsyncClient, me: dict, friend: dict, lore: dict, **scenario) -> dict:
    """둘이 앉아 시작한 테이블. 맵을 따로 주지 않으면 the_map 이다."""
    table = await open_duo(client, me, friend, lore, **(scenario or the_map(lore)))
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def move(client: AsyncClient, headers: dict, table: dict, user_id: uuid.UUID, place: dict):
    """방장이 캐릭터를 옮기는 요청. 응답을 그대로 돌려준다."""
    url = table_url(table, f'/members/{user_id}/place')
    return await client.put(url, json={'place_id': place['id']}, headers=headers)


def place_of(table: dict, user_id: uuid.UUID) -> str | None:
    """그 사람의 지금 캐릭터가 서 있는 장소의 ID."""
    member = next(member for member in table['members'] if member['user_id'] == str(user_id))
    return member['sheet']['place_id']


def known_places(table: dict) -> list[str]:
    """테이블이 아는 장소들의 이름. 판의 순서다."""
    return [place['name'] for place in table['map']['places']]


def known_routes(table: dict, lore: dict) -> list[tuple[str, str, bool]]:
    """테이블이 아는 길들을 (어디서, 어디로, 양쪽인가)로. 장소는 로어북 픽스처의 이름표다."""
    label = {entry['id']: key for key, entry in lore.items() if isinstance(entry, dict) and 'id' in entry}
    return [(label[item['from_place']], label[item['to_place']], item['two_way']) for item in table['map']['routes']]


def refused(response, reason: str) -> bool:
    """409 이고 그 까닭인가."""
    return response.status_code == status.HTTP_409_CONFLICT and response.json()['reason'] == reason


# --- 시작 ---


async def test_everyone_starts_at_the_start_place(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    assert place_of(table, ME) == place_of(table, FRIEND) == lore['gate']['id']


async def test_before_the_start_only_what_is_open_is_known(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await open_duo(client, me, friend, lore, **the_map(lore))

    detail = await read_table(client, me, table)

    # 아무도 서 보지 않았다. 시작 장소, 큰길과 그 끝, 명소만 안다. 성문의 안개 길은 아직 모른다
    assert known_places(detail) == ['성문', '광장', '탑']
    assert known_routes(detail, lore) == [('gate', 'square', True)]


async def test_a_start_alone_is_known_before_the_start(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await open_duo(client, me, friend, lore, start_place=lore['square']['id'])

    detail = await read_table(client, me, table)

    # 길이 없는 맵이다. 시작 장소는 처음부터 안다
    assert (known_places(detail), detail['map']['routes']) == (['광장'], [])


# --- 아는 것 ---


async def test_standing_at_the_start_shows_its_fog_routes(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    # 성문에 섰다. 성문에서 나가는 안개 길(숲)이 보이고, 그 끝인 숲을 안다. 숲 너머의 오두막은 아직 모른다
    assert known_places(table) == ['성문', '광장', '숲', '탑']
    assert known_routes(table, lore) == [('gate', 'square', True), ('gate', 'forest', True)]


async def test_hidden_routes_and_places_never_leave_even_for_the_host(
    client: AsyncClient, me: dict, friend: dict, lore: dict
):
    table = await start_duo(client, me, friend, lore)
    await move(client, me, table, ME, lore['square'])

    host_view = await read_table(client, me, table)
    player_view = await read_table(client, friend, table)

    # 지하실로 가는 숨긴 길의 한쪽 끝(광장)에 서도 숨긴 길은 모른다. 찾아야 안다
    assert host_view['map'] == player_view['map']
    assert '지하실' not in known_places(host_view)
    for leaked in (host_view, player_view, await events_of(client, me, table, 'character_moved')):
        assert lore['cellar']['id'] not in json.dumps(leaked, ensure_ascii=False)


async def test_standing_somewhere_new_reveals_its_fog_routes_for_good(
    client: AsyncClient, me: dict, friend: dict, lore: dict
):
    table = await start_duo(client, me, friend, lore)

    await move(client, me, table, ME, lore['forest'])
    back = await move(client, me, table, ME, lore['gate'])

    # 숲에 섰다가 돌아와도 숲-오두막의 길과 오두막은 계속 안다. 테이블의 모두가 함께 안다
    assert known_places(back.json()) == ['성문', '광장', '숲', '오두막', '탑']
    assert ('hut', 'forest', True) in known_routes(back.json(), lore)
    assert known_places(await read_table(client, friend, table)) == known_places(back.json())


# --- 방장이 옮기기 ---


async def test_the_host_moves_a_character_and_everyone_sees_it(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await move(client, me, table, FRIEND, lore['forest'])

    assert response.status_code == status.HTTP_200_OK, response.text
    assert (place_of(response.json(), FRIEND), place_of(response.json(), ME)) == (
        lore['forest']['id'],
        lore['gate']['id'],
    )
    [event] = await events_of(client, friend, table, 'character_moved')
    assert event['actor_id'] == str(ME)
    assert event['payload'] == {
        'user_id': str(FRIEND),
        'character_name': '약사',
        'from': {'entry_id': lore['gate']['id'], 'name': '성문'},
        'to': {'entry_id': lore['forest']['id'], 'name': '숲'},
    }


async def test_a_landmark_can_be_reached_without_a_route(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    # 방장이 옮기는 것은 이야기가 건너뛴 이동이다. 길로 이어져 있지 않아도 아는 곳이면 된다
    response = await move(client, me, table, ME, lore['tower'])

    assert place_of(response.json(), ME) == lore['tower']['id']


@pytest.mark.parametrize('where', ['cellar', 'hut', 'potion', 'nowhere'])
async def test_only_known_places_can_be_reached(client: AsyncClient, me: dict, friend: dict, lore: dict, where: str):
    table = await start_duo(client, me, friend, lore)
    target = lore.get(where, {'id': NO_SUCH_ID})

    response = await move(client, me, table, ME, target)

    # 숨긴 곳, 아직 모르는 곳, 장소가 아닌 것, 없는 것이 같은 답이다. 다르면 숨긴 장소가 있다는 것이 드러난다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'place_id 에 고를 수 없는 값이 있습니다.'}
    assert place_of(await read_table(client, me, table), ME) == lore['gate']['id']
    assert await events_of(client, me, table, 'character_moved') == []


async def test_moving_to_the_same_place_changes_nothing(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await move(client, me, table, ME, lore['gate'])

    assert response.status_code == status.HTTP_200_OK
    assert await events_of(client, me, table, 'character_moved') == []


async def test_a_downed_character_is_carried_but_a_dead_one_stays(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await session.execute(text('UPDATE table_sheets SET hp = 0 WHERE user_id = :user_id'), {'user_id': ME})
    await session.commit()
    await kill(session, FRIEND)

    carried = await move(client, me, table, ME, lore['square'])
    left = await move(client, me, table, FRIEND, lore['square'])

    assert place_of(carried.json(), ME) == lore['square']['id']
    assert refused(left, 'character_dead')


async def test_only_the_host_moves_characters_while_playing(
    client: AsyncClient, me: dict, friend: dict, stranger: dict, lore: dict
):
    waiting = await open_duo(client, me, friend, lore, **the_map(lore))
    assert refused(await move(client, me, waiting, ME, lore['gate']), 'not_playing')

    table = await start_duo(client, me, friend, lore)
    assert (await move(client, friend, table, FRIEND, lore['square'])).status_code == status.HTTP_403_FORBIDDEN
    assert (await move(client, stranger, table, FRIEND, lore['square'])).status_code == status.HTTP_404_NOT_FOUND
    assert (await move(client, me, table, STRANGER, lore['square'])).status_code == status.HTTP_404_NOT_FOUND

    await client.post(table_url(table, '/end'), headers=me)
    assert refused(await move(client, me, table, ME, lore['square']), 'not_playing')


async def test_a_character_from_before_the_map_is_moved_from_nowhere(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    # 맵이 생기기 전에 시작한 테이블의 캐릭터는 위치가 없다
    await session.execute(text('UPDATE table_sheets SET place_id = NULL WHERE user_id = :user_id'), {'user_id': ME})
    await session.commit()

    await move(client, me, table, ME, lore['square'])

    [event] = await events_of(client, me, table, 'character_moved')
    assert (event['payload']['from'], event['payload']['to']['name']) == (None, '광장')


# --- 새 캐릭터 ---


async def test_a_new_character_joins_where_the_last_one_fell(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await move(client, me, table, FRIEND, lore['forest'])
    await kill(session, FRIEND)

    arrived = await client.post(table_url(table, '/character'), json={'name': '새 약사'}, headers=friend)

    assert arrived.status_code == status.HTTP_201_CREATED, arrived.text
    assert place_of(arrived.json(), FRIEND) == lore['forest']['id']
    [event] = await events_of(client, me, table, 'character_joined')
    assert event['payload']['place'] == {'entry_id': lore['forest']['id'], 'name': '숲'}


# --- 맵이 없는 판 ---


async def test_a_table_without_a_map_has_no_places(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore, start_place=None)

    assert (table['map'], place_of(table, ME)) == (None, None)
    assert (await move(client, me, table, ME, lore['gate'])).status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # 새 캐릭터에게도 위치가 없다
    await kill(session, FRIEND)
    arrived = await client.post(table_url(table, '/character'), json={'name': '새 약사'}, headers=friend)
    assert place_of(arrived.json(), FRIEND) is None
    [event] = await events_of(client, me, table, 'character_joined')
    assert event['payload']['place'] is None
