# trpg-server/tests/test_table_items.py

"""
테이블의 소지품(#202).

넷을 본다.
  - 시작 소지품: 시작할 때 판의 시작 소지품과 고른 프리젠의 소지품을 받는다. 새 캐릭터는 물려받지 않고 새로 받는다.
  - 방장이 주고 빼앗기: 진행 중에, 살아 있는 캐릭터에게, 판의 물건만, 한 가지 99 개까지. 이벤트로 남는다.
  - 보이기: 앉은 사람 모두가 서로의 소지품과 판의 물건 목록을 본다. 물건의 설명(로어북의 글)은 나가지 않는다.
  - 서술: 닫기 시작할 때의 소지품이 서술자에게 간다. 없는 물건을 쓰지 말라는 다루는 법이 붙는다.
"""

import asyncio
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import ItemStackSnapshot
from app.main import API_PREFIX
from app.rounds import prompt
from app.rounds.move_lines import describe_items
from app.rounds.narration_request import read_moves
from app.rounds.narrator import ItemNote, Move, NarrationRequest
from app.tables.items import starting_stacks
from app.tables.models import TableItem
from tests.narration_model import asset_body
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 로어북 항목의 글. AI 가 읽는 설정이다. 플레이어에게 나가지 않는지 본다
POTION_SECRET = '사실 이 물약은 독이다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장의 머리말. 직접 만든 캐릭터(기사)를 한다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """프리젠(약사)을 고르는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """물건 셋(치유 물약, 밧줄, 등불)과 인물 하나가 든 로어북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='모험의 물건들')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str, content: str = '') -> dict:
        return await post(client, url, me, name=name, keywords=[], content=content or f'{name}의 설명', kind=kind)

    return {
        'lorebook': lorebook,
        'potion': await entry('치유 물약', 'item', POTION_SECRET),
        'rope': await entry('밧줄', 'item'),
        'lamp': await entry('등불', 'item'),
        'lady': await entry('악역영애', 'person'),
    }


async def open_duo(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """
    둘이 앉은 테이블. 시작하지 않았다.

    판: 물약은 소모품(가벼움만큼 회복), 밧줄은 장비, 등불은 규칙이 없다(장비).
    시작 소지품은 밧줄 하나. 프리젠 약사는 물약 둘을, 사냥꾼은 등불 하나를 더 받는다.
    나는 직접 만들고, 친구는 약사를 고른다. 사냥꾼은 남는다.
    """
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '물건의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['시장이다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'lorebook_ids': [lore['lorebook']['id']],
        'items': [
            {'entry_id': lore['potion']['id'], 'kind': 'consumable', 'heals': 'light'},
            {'entry_id': lore['rope']['id'], 'kind': 'gear'},
        ],
        'starting_items': [{'entry_id': lore['rope']['id'], 'count': 1}],
        'pregens': [
            {'name': '약사', 'sheet': SHEET, 'items': [{'entry_id': lore['potion']['id'], 'count': 2}]},
            {'name': '사냥꾼', 'sheet': SHEET, 'items': [{'entry_id': lore['lamp']['id'], 'count': 1}]},
        ],
    }
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2)
    joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    assert joined.status_code == status.HTTP_200_OK, joined.text
    await client.put(table_url(table, '/character'), json={'name': '기사'}, headers=me)
    picked = await client.put(table_url(table, '/character'), json={'pregen_index': 0}, headers=friend)
    assert picked.status_code == status.HTTP_200_OK, picked.text
    return table


async def start_duo(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """둘이 앉아 시작한 테이블. 첫 라운드가 열려 있다."""
    table = await open_duo(client, me, friend, lore)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


def held(table: dict, user_id: uuid.UUID) -> list[tuple[str, int]]:
    """그 사람의 지금 캐릭터가 가진 것을 (이름, 개수)로."""
    member = next(member for member in table['members'] if member['user_id'] == str(user_id))
    return [(item['name'], item['count']) for item in member['sheet']['items']]


async def read_table(client: AsyncClient, headers: dict, table: dict) -> dict:
    response = await client.get(table_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def give(client: AsyncClient, headers: dict, table: dict, user_id: uuid.UUID, entry: dict, count: int = 1):
    """방장이 물건을 주는 요청. 응답을 그대로 돌려준다."""
    body = {'entry_id': entry['id'], 'count': count}
    return await client.post(table_url(table, f'/members/{user_id}/items'), json=body, headers=headers)


async def take(client: AsyncClient, headers: dict, table: dict, user_id: uuid.UUID, entry: dict, count: int = 1):
    """방장이 물건을 빼앗는 요청. 응답을 그대로 돌려준다."""
    url = table_url(table, f'/members/{user_id}/items/{entry["id"]}')
    return await client.delete(url, params={'count': count}, headers=headers)


async def events_of(client: AsyncClient, headers: dict, table: dict, kind: str) -> list[dict]:
    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=headers)
    return [event for event in response.json()['items'] if event['type'] == kind]


async def kill(session: AsyncSession, user_id: uuid.UUID) -> None:
    """서비스를 거치지 않고 그 사람의 캐릭터를 죽인다. 쓰러져 죽은 것과 같은 값이다."""
    await session.execute(
        text('UPDATE table_sheets SET hp = 0, died_at = now() WHERE user_id = :user_id'), {'user_id': user_id}
    )
    await session.commit()


# --- 시작 소지품 ---


async def test_everyone_starts_with_the_starting_items_and_pregens_with_theirs(
    client: AsyncClient, me: dict, friend: dict, lore: dict
):
    table = await start_duo(client, me, friend, lore)

    assert held(table, ME) == [('밧줄', 1)]
    assert held(table, FRIEND) == [('치유 물약', 2), ('밧줄', 1)]


async def test_the_table_lists_the_things_of_its_version(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await open_duo(client, me, friend, lore)

    read = await read_table(client, friend, table)

    # 물건 항목만 나온다. 규칙이 없는 등불은 장비다
    assert read['items'] == [
        {
            'entry_id': lore['potion']['id'],
            'name': '치유 물약',
            'kind': 'consumable',
            'heals': 'light',
            'rarity': 'normal',
        },
        {'entry_id': lore['rope']['id'], 'name': '밧줄', 'kind': 'gear', 'heals': None, 'rarity': 'normal'},
        {'entry_id': lore['lamp']['id'], 'name': '등불', 'kind': 'gear', 'heals': None, 'rarity': 'normal'},
    ]


async def test_the_description_of_a_thing_is_not_shown(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await client.get(table_url(table), headers=friend)

    # 로어북의 글은 AI 가 읽는 설정이다. 비밀이 들어 있을 수 있다
    assert POTION_SECRET not in response.text


def test_starting_items_add_up_with_the_pregens_and_stop_at_the_limit():
    rope, potion = uuid.uuid4(), uuid.uuid4()

    class Pregen:
        items = [ItemStackSnapshot(entry_id=rope, count=60), ItemStackSnapshot(entry_id=potion, count=1)]

    class Version:
        starting_items = [ItemStackSnapshot(entry_id=rope, count=60)]
        pregens = [Pregen]

    stacks = starting_stacks(Version, 0)

    assert [(stack.entry_id, stack.count) for stack in stacks] == [(rope, 99), (potion, 1)]
    assert [(stack.entry_id, stack.count) for stack in starting_stacks(Version, None)] == [(rope, 60)]


async def test_a_new_character_does_not_inherit_but_starts_afresh(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await give(client, me, table, FRIEND, lore['lamp'])
    await kill(session, FRIEND)

    arrived = await client.post(table_url(table, '/character'), json={'name': '새 기사'}, headers=friend)

    assert arrived.status_code == status.HTTP_201_CREATED, arrived.text
    # 직접 만든 새 캐릭터는 판의 시작 소지품만 받는다. 앞 캐릭터의 물약과 등불은 따라오지 않는다
    assert held(arrived.json(), FRIEND) == [('밧줄', 1)]
    # 죽은 캐릭터의 소지품은 그 시트와 함께 남는다
    query = select(TableItem.count).where(TableItem.table_id == uuid.UUID(table['id']))
    assert sorted(await session.scalars(query)) == [1, 1, 1, 1, 2]


async def test_a_new_character_from_a_pregen_gets_its_items(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await kill(session, ME)

    arrived = await client.post(table_url(table, '/character'), json={'pregen_index': 1}, headers=me)

    assert arrived.status_code == status.HTTP_201_CREATED, arrived.text
    assert held(arrived.json(), ME) == [('밧줄', 1), ('등불', 1)]


# --- 방장이 주고 빼앗기 ---


async def test_the_host_gives_and_everyone_is_told(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await give(client, me, table, FRIEND, lore['potion'], 3)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert held(response.json(), FRIEND) == [('치유 물약', 5), ('밧줄', 1)]
    (gained,) = await events_of(client, friend, table, 'items_gained')
    assert gained['actor_id'] == str(ME)
    assert gained['payload'] == {
        'user_id': str(FRIEND),
        'character_name': '약사',
        'entry_id': lore['potion']['id'],
        'name': '치유 물약',
        'count': 3,
        'total': 5,
    }


async def test_things_are_listed_in_the_order_of_the_version(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    await give(client, me, table, ME, lore['lamp'])
    response = await give(client, me, table, ME, lore['potion'])

    # 받은 순서(밧줄, 등불, 물약)가 아니라 판의 물건 순서다
    assert held(response.json(), ME) == [('치유 물약', 1), ('밧줄', 1), ('등불', 1)]


async def test_the_host_takes_away_and_an_empty_line_goes(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    once = await take(client, me, table, FRIEND, lore['potion'])
    again = await take(client, me, table, FRIEND, lore['potion'])

    assert held(once.json(), FRIEND) == [('치유 물약', 1), ('밧줄', 1)]
    assert held(again.json(), FRIEND) == [('밧줄', 1)]
    lost = await events_of(client, friend, table, 'items_lost')
    assert [(event['payload']['count'], event['payload']['total']) for event in lost] == [(1, 1), (1, 0)]


@pytest.mark.parametrize(('entry', 'count'), [('potion', 3), ('lamp', 1)], ids=['more-than-held', 'not-held'])
async def test_cannot_take_more_than_is_held(client: AsyncClient, me: dict, friend: dict, lore: dict, entry, count):
    table = await start_duo(client, me, friend, lore)

    response = await take(client, me, table, FRIEND, lore[entry], count)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'not_enough_items' in response.text
    assert held(await read_table(client, me, table), FRIEND) == [('치유 물약', 2), ('밧줄', 1)]


async def test_one_thing_stops_at_ninety_nine(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)
    await give(client, me, table, FRIEND, lore['potion'], 97)

    over = await give(client, me, table, FRIEND, lore['potion'], 1)

    assert over.status_code == status.HTTP_409_CONFLICT
    assert 'too_many_items' in over.text
    assert held(await read_table(client, me, table), FRIEND) == [('치유 물약', 99), ('밧줄', 1)]


async def test_only_the_host_gives_or_takes(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    giving = await give(client, friend, table, FRIEND, lore['potion'])
    taking = await take(client, friend, table, ME, lore['rope'])

    assert (giving.status_code, taking.status_code) == (status.HTTP_403_FORBIDDEN, status.HTTP_403_FORBIDDEN)
    assert await events_of(client, me, table, 'items_gained') == []


async def test_nothing_is_given_before_the_start(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await open_duo(client, me, friend, lore)

    response = await give(client, me, table, FRIEND, lore['potion'])

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'not_playing' in response.text


async def test_nothing_is_given_after_the_end(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)
    await client.post(table_url(table, '/end'), headers=me)

    response = await give(client, me, table, FRIEND, lore['potion'])

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_only_to_someone_seated(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await give(client, me, table, STRANGER, lore['potion'])

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_nothing_for_the_dead(client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession):
    table = await start_duo(client, me, friend, lore)
    await kill(session, FRIEND)

    giving = await give(client, me, table, FRIEND, lore['potion'])
    taking = await take(client, me, table, FRIEND, lore['potion'])

    assert (giving.status_code, taking.status_code) == (status.HTTP_409_CONFLICT, status.HTTP_409_CONFLICT)
    assert 'character_dead' in giving.text


@pytest.mark.parametrize('entry', ['lady', 'unknown'])
async def test_only_things_of_the_version(client: AsyncClient, me: dict, friend: dict, lore: dict, entry: str):
    table = await start_duo(client, me, friend, lore)
    target = {'id': NO_SUCH_ID} if entry == 'unknown' else lore[entry]

    response = await give(client, me, table, FRIEND, target)

    # 인물이나 판에 없는 것은 소지품이 될 수 없다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'entry_id' in response.text


@pytest.mark.parametrize('count', [0, 100])
async def test_rejects_a_bad_count(client: AsyncClient, me: dict, friend: dict, lore: dict, count: int):
    table = await start_duo(client, me, friend, lore)

    giving = await give(client, me, table, FRIEND, lore['potion'], count)
    taking = await take(client, me, table, FRIEND, lore['potion'], count)

    assert (giving.status_code, taking.status_code) == (422, 422)


async def test_two_gifts_at_once_are_counted_one_after_the_other(
    client: AsyncClient, me: dict, friend: dict, lore: dict
):
    table = await start_duo(client, me, friend, lore)

    # 둘 다 60 개를 준다. 하나씩 차례로 세면 둘째는 상한을 넘어 거절된다. 잠그지 않으면 둘 다 "2 개"를 보고 덮어쓴다
    first, second = await asyncio.gather(
        give(client, me, table, FRIEND, lore['potion'], 60), give(client, me, table, FRIEND, lore['potion'], 60)
    )

    assert sorted([first.status_code, second.status_code]) == [status.HTTP_200_OK, status.HTTP_409_CONFLICT]
    assert held(await read_table(client, me, table), FRIEND) == [('치유 물약', 62), ('밧줄', 1)]


async def test_items_leave_with_the_person(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)

    await client.delete(table_url(table, '/members/me'), headers=friend)

    query = select(TableItem.count).where(TableItem.table_id == uuid.UUID(table['id']))
    assert list(await session.scalars(query)) == [1]


# --- 서술 ---


async def test_the_narrator_hears_what_each_one_holds(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore)
    url = table_url(table, '/rounds/current/declaration')

    await client.put(url, json={'content': '주위를 살핀다.'}, headers=me)
    await client.put(url, json={'content': '물약을 흔든다.'}, headers=friend)
    await narrated()

    # 가짜 서술자는 받은 것을 그대로 늘어놓는다
    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '기사: 주위를 살핀다. [소지품: 밧줄]' in second['scene']
    assert '약사: 물약을 흔든다. [소지품: 치유 물약 2개, 밧줄]' in second['scene']


def test_one_of_a_thing_has_no_count():
    assert describe_items([ItemNote('밧줄', 1), ItemNote('치유 물약', 2)]) == '밧줄, 치유 물약 2개'


def request_with(*moves: Move) -> NarrationRequest:
    return NarrationRequest(round_number=1, scene='시장이다.', moves=list(moves))


def test_the_prompt_says_how_to_treat_items_only_when_someone_holds_some():
    holding = prompt.round_text(request_with(Move('기사', '살핀다.', items=[ItemNote('밧줄', 1)])))
    empty = prompt.round_text(request_with(Move('기사', '살핀다.')))

    assert '[소지품: 밧줄]' in holding
    assert prompt.ITEMS_NOTE in holding
    assert prompt.ITEMS_NOTE not in empty


def test_a_round_frozen_before_items_reads_without_them():
    # 소지품이 생기기 전에 닫기 시작한 라운드에 굳혀 둔 것이다
    (move,) = read_moves([{'character_name': '기사', 'content': '살핀다.'}])

    assert move.items == []


# --- DB 의 마지막 방어선 ---


async def first_sheet_id(session: AsyncSession, table: dict) -> uuid.UUID:
    query = text('SELECT id FROM table_sheets WHERE table_id = :table_id AND user_id = :me')
    return await session.scalar(query, {'table_id': table['id'], 'me': ME})


@pytest.mark.parametrize('count', [0, 100])
async def test_the_database_rejects_a_count_out_of_range(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession, count: int
):
    table = await start_duo(client, me, friend, lore)
    sheet_id = await first_sheet_id(session, table)

    session.add(TableItem(table_id=uuid.UUID(table['id']), sheet_id=sheet_id, entry_id=uuid.uuid4(), count=count))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_two_lines_of_one_thing(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    sheet_id = await first_sheet_id(session, table)

    # 시작할 때 이미 밧줄의 줄이 있다
    session.add(
        TableItem(table_id=uuid.UUID(table['id']), sheet_id=sheet_id, entry_id=uuid.UUID(lore['rope']['id']), count=1)
    )

    with pytest.raises(IntegrityError):
        await session.commit()
