# asset-server/tests/test_shortcuts.py

"""
단축어(app/shortcuts/, #981)를 검증한다. 실제 DB(asset_test)에서 돈다. 서명 자체는 tests/test_service_auth.py 가 본다.

보는 것.
  - 내 단축어: 적지 않았으면 빈 목록, 통째로 바꾸고 읽는다(앞뒤 빈칸을 뗀다). 로그인해야 한다
  - 같은 이름, 21개, 빈칸이나 / 가 든 이름, 긴 이름·설명·본문, 빈 본문, 모르는 칸은 422 이고 아무것도 바뀌지 않는다
  - 다른 서버(chat, story)는 서명과 사용자의 토큰으로 그 사람의 단축어를 가져간다
  - 제작자 단축어: 캐릭터와 세계관의 초안에 적고 고친다. 게시하면 판의 문서에 굳는다(캐릭터 형식 10, 세계관 형식 8)
  - 탈퇴하면 내 단축어를 지운다
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.documents import DOCUMENT_FORMAT as CHARACTER_FORMAT
from app.main import API_PREFIX
from app.shortcuts.models import UserShortcuts
from app.withdrawal.service import erase_belongings
from app.worlds.documents import DOCUMENT_FORMAT as WORLD_FORMAT
from tests.signing import signed_get
from tests.worlds import CHARACTERS_URL, OTHER, OWNER, bearer, character, create_world, full_world, publish

pytestmark = pytest.mark.usefixtures('clean_tables')

SHORTCUTS_URL = f'{API_PREFIX}/shortcuts'
DIARY = {'name': '일기', 'description': '오늘을 일기로', 'body': '지금까지의 일을 캐릭터의 일기로 써 줘.'}
FLASHBACK = {'name': '플래시백', 'body': '캐릭터의 어린 시절 한 장면을 회상으로 보여 줘.'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OTHER)


async def put_mine(client: AsyncClient, headers: dict, items: list[dict]):
    return await client.put(SHORTCUTS_URL, json={'items': items}, headers=headers)


async def test_my_shortcuts_start_empty_and_are_replaced_whole(client: AsyncClient, mine: dict, theirs: dict):
    empty = await client.get(SHORTCUTS_URL, headers=mine)

    first = await put_mine(client, mine, [{**DIARY, 'name': ' 일기 '}, FLASHBACK])
    replaced = await put_mine(client, mine, [FLASHBACK])
    read = await client.get(SHORTCUTS_URL, headers=mine)

    assert (empty.status_code, empty.json()) == (status.HTTP_200_OK, {'items': []})
    assert first.json()['items'] == [DIARY, {**FLASHBACK, 'description': ''}]
    assert replaced.status_code == status.HTTP_200_OK
    assert read.json() == {'items': [{**FLASHBACK, 'description': ''}]}
    # 남의 것은 따로다
    assert (await client.get(SHORTCUTS_URL, headers=theirs)).json() == {'items': []}


async def test_shortcuts_need_login(client: AsyncClient):
    assert (await client.get(SHORTCUTS_URL)).status_code == status.HTTP_401_UNAUTHORIZED
    assert (await put_mine(client, {}, [DIARY])).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.parametrize(
    'items',
    [
        [DIARY, {**FLASHBACK, 'name': '일기'}],
        [{**DIARY, 'name': f'단축{number}'} for number in range(21)],
        [{**DIARY, 'name': '오늘 일기'}],
        [{**DIARY, 'name': '일/기'}],
        [{**DIARY, 'name': '가' * 11}],
        [{**DIARY, 'name': ''}],
        [{**DIARY, 'description': '가' * 31}],
        [{**DIARY, 'body': '가' * 401}],
        [{**DIARY, 'body': '   '}],
        [{**DIARY, 'secret': '시스템 지시'}],
    ],
)
async def test_bad_shortcuts_are_refused_and_change_nothing(client: AsyncClient, mine: dict, items: list[dict]):
    await put_mine(client, mine, [DIARY])

    response = await put_mine(client, mine, items)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await client.get(SHORTCUTS_URL, headers=mine)).json() == {'items': [DIARY]}


async def test_other_servers_take_the_token_owner_s_shortcuts(client: AsyncClient, mine: dict, theirs: dict):
    await put_mine(client, mine, [DIARY])

    taken = await signed_get(client, '/shortcuts', mine, caller='story')
    others = await signed_get(client, '/shortcuts', theirs)
    unsigned = await client.get(f'{API_PREFIX}/service/chat/shortcuts', headers=mine)

    assert (taken.status_code, taken.json()) == (status.HTTP_200_OK, {'items': [DIARY]})
    assert others.json() == {'items': []}
    assert unsigned.status_code == status.HTTP_401_UNAUTHORIZED


async def test_character_shortcuts_are_kept_in_the_draft_and_frozen_in_the_version(client: AsyncClient, mine: dict):
    made = await character(client, mine, published=False, shortcuts=[DIARY])
    url = f'{CHARACTERS_URL}/{made["id"]}'

    duplicated = await client.patch(url, json={'shortcuts': [DIARY, DIARY]}, headers=mine)
    changed = await client.patch(url, json={'shortcuts': [DIARY, FLASHBACK]}, headers=mine)
    published = await client.post(f'{url}/versions', json={}, headers=mine)
    await client.patch(url, json={'shortcuts': []}, headers=mine)
    frozen = (await client.get(f'{url}/versions/1', headers=mine)).json()['document']

    assert made['shortcuts'] == [DIARY]
    assert duplicated.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert [shortcut['name'] for shortcut in changed.json()['shortcuts']] == ['일기', '플래시백']
    assert published.status_code == status.HTTP_201_CREATED, published.text
    # 판에 굳은 단축어는 초안을 고쳐도 그대로다
    assert frozen['format'] == CHARACTER_FORMAT >= 10
    assert [shortcut['name'] for shortcut in frozen['shortcuts']] == ['일기', '플래시백']


async def test_world_shortcuts_are_frozen_in_the_version(client: AsyncClient, mine: dict):
    ari, beo = await character(client, mine, '아리'), await character(client, mine, '버')
    world = await create_world(client, mine, {**full_world(ari['id'], beo['id']), 'shortcuts': [FLASHBACK]})
    refused = await client.patch(
        f'{API_PREFIX}/worlds/{world["id"]}', json={'shortcuts': [{**DIARY, 'name': '일 기'}]}, headers=mine
    )

    response = await publish(client, mine, world)
    frozen = (await client.get(f'{API_PREFIX}/worlds/{world["id"]}/versions/1', headers=mine)).json()['document']

    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.status_code == status.HTTP_201_CREATED, response.text
    # 단축어는 형식 8 부터다. 뒤의 형식(9 의 업적)에도 그대로 실린다
    assert frozen['shortcuts'] == [{**FLASHBACK, 'description': ''}]
    assert frozen['format'] == WORLD_FORMAT >= 8


async def test_withdrawal_erases_my_shortcuts(client: AsyncClient, session: AsyncSession, mine: dict, theirs: dict):
    await put_mine(client, mine, [DIARY])
    await put_mine(client, theirs, [FLASHBACK])

    await erase_belongings(session, OWNER)

    owners = await session.scalars(select(UserShortcuts.owner_id))
    assert list(owners) == [OTHER]
    assert await session.scalar(select(func.count()).select_from(UserShortcuts)) == 1
