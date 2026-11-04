# asset-server/tests/test_creator_stats.py

"""
제작자 숫자(app/creator_stats/, #991)를 검증한다. 실제 DB(asset_test)에서 돈다.

  - 내 캐릭터(세계관)마다 받아 둔 시작 수(work_starts)의 모든 수와 최근의 수다. 받은 시각이 함께 온다
  - 최근의 수가 많은 것부터, 같으면 모든 수가 많은 것부터다. 더한 수가 함께 온다
  - 게시한 적이 있거나 받은 수가 있는 것만이다. 게시하지 않은 초안은 빠진다. 남의 작품은 들지 않는다
  - 한 번도 받지 못했으면 수가 0 이고 refreshed_at 이 null 이다. 로그인해야 한다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.creator_stats.service import MAX_STATS_ITEMS, summarize
from app.main import API_PREFIX
from app.stats.models import WorkKind
from tests import test_characters_api as character_tests
from tests.test_characters_api import create, make_public
from tests.test_rankings import NOW, seed
from tests.test_world_listings import published
from tests.worlds import OTHER, OWNER, bearer, create_world, full_world
from tests.worlds import character as world_character

pytestmark = pytest.mark.usefixtures('clean_tables')

operator = character_tests.operator
player = character_tests.player

STATS_URL = f'{API_PREFIX}/me/stats'


async def stats(client: AsyncClient, kind: str, headers: dict) -> dict:
    response = await client.get(f'{STATS_URL}/{kind}', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def rows(body: dict) -> list[tuple[str, int, int]]:
    return [(item['title'], item['total'], item['recent']) for item in body['items']]


async def test_counts_my_characters(client: AsyncClient, session: AsyncSession, operator: dict, player: dict):
    quiet = await make_public(client, operator, name='조용한')
    busy = await make_public(client, operator, name='바쁜')
    old = await make_public(client, operator, name='지난')
    await create(client, operator, name='초안')
    await seed(session, WorkKind.CHARACTER, (busy['id'], 5, 3), (old['id'], 9, 0), (str(uuid.uuid4()), 4, 4))

    body = await stats(client, 'characters', operator)

    assert body['recent_days'] == 7
    assert body['refreshed_at'] == NOW.isoformat().replace('+00:00', 'Z')
    assert (body['total'], body['recent']) == (14, 3)
    assert rows(body) == [('바쁜', 5, 3), ('지난', 9, 0), ('조용한', 0, 0)]
    assert [item['id'] for item in body['items']][-1] == quiet['id']
    # 남의 것(운영자의 캐릭터)은 들지 않는다. 받은 시각은 그 종류에 하나라 함께 온다
    mine = await stats(client, 'characters', player)
    assert (mine['items'], mine['total']) == ([], 0)


async def test_counts_my_worlds(client: AsyncClient, session: AsyncSession, signing_key: SigningKey):
    owner, other = bearer(signing_key, OWNER), bearer(signing_key, OTHER)
    summer = await published(client, owner, name='여름')
    ari, beo = await world_character(client, owner, '아리'), await world_character(client, owner, '버')
    draft = await create_world(client, owner, {**full_world(ari['id'], beo['id']), 'name': '초안'})
    theirs = await published(client, other, name='남의 여름')
    await seed(session, WorkKind.WORLD, (summer['id'], 2, 1), (draft['id'], 1, 1), (theirs['id'], 7, 7))

    body = await stats(client, 'worlds', owner)

    # 초안이어도 받은 수가 있으면 든다(게시했다가 지운 판의 수일 수 있다)
    assert rows(body) == [('여름', 2, 1), ('초안', 1, 1)]
    assert (body['total'], body['recent']) == (3, 2)
    assert rows(await stats(client, 'worlds', other)) == [('남의 여름', 7, 7)]


async def test_never_received_is_zero(client: AsyncClient, operator: dict):
    await make_public(client, operator, name='새것')

    body = await stats(client, 'characters', operator)

    assert body == {
        'recent_days': 7,
        'refreshed_at': None,
        'total': 0,
        'recent': 0,
        'items': [{'id': body['items'][0]['id'], 'title': '새것', 'total': 0, 'recent': 0}],
    }


@pytest.mark.parametrize('kind', ['characters', 'worlds'])
async def test_needs_login(client: AsyncClient, kind: str):
    response = await client.get(f'{STATS_URL}/{kind}')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_sums_every_row_but_lists_only_the_first():
    many = [(uuid.uuid4(), f'작품 {index}', 2, 1) for index in range(MAX_STATS_ITEMS + 5)]

    summary = summarize(many, None)

    assert (summary.total, summary.recent) == (2 * len(many), len(many))
    assert len(summary.items) == MAX_STATS_ITEMS
