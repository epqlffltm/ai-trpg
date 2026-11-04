# trpg-server/tests/test_creator_stats.py

"""
제작자 숫자(app/creator_stats/, #991)를 검증한다. 실제 DB(game_test)에서 돈다.

  - 내 시나리오마다 연 테이블의 모든 수와 최근 7일의 수다. 누가 열었든 센다. 7일보다 앞의 것은 최근의 수에 들지 않는다
  - 최근의 수가 많은 것부터, 같으면 모든 수가 많은 것부터다. 더한 수가 함께 온다
  - 지금 공개 중이거나 한 번이라도 열린 것만이다. 초안만 있는 것은 빠진다. 공개를 내려도 열린 적이 있으면 남는다
  - 남의 시나리오는 들지 않는다. 로그인해야 한다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.creator_stats.service import MAX_STATS_ITEMS, summarize
from app.main import API_PREFIX
from tests import test_listings_api as listing_tests
from tests.test_listings_api import create_scenario, listing_url, make_public
from tests.test_rankings import age, open_tables

pytestmark = pytest.mark.usefixtures('clean_tables')

my_headers = listing_tests.my_headers
their_headers = listing_tests.their_headers

STATS_URL = f'{API_PREFIX}/me/stats/scenarios'
TABLES_URL = f'{API_PREFIX}/tables'


async def stats(client: AsyncClient, headers: dict) -> dict:
    response = await client.get(STATS_URL, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def open_as_guest(client: AsyncClient, headers: dict, scenario: dict, count: int) -> None:
    """남이 공개 중인 판으로 테이블을 count 개 연다(판의 번호를 적지 않는다)."""
    for _ in range(count):
        body = {'scenario_id': scenario['id'], 'capacity': 2}
        response = await client.post(TABLES_URL, json=body, headers=headers)
        assert response.status_code == status.HTTP_201_CREATED, response.text


def rows(body: dict) -> list[tuple[str, int, int]]:
    return [(item['title'], item['total'], item['recent']) for item in body['items']]


async def test_counts_my_scenarios_by_tables_opened(
    client: AsyncClient, session: AsyncSession, my_headers: dict, their_headers: dict
):
    busy = await make_public(client, my_headers, title='이번 주')
    old = await make_public(client, my_headers, title='지난달')
    await make_public(client, my_headers, title='아직 아무도')
    down = await make_public(client, my_headers, title='내림')
    await create_scenario(client, my_headers, title='초안')
    theirs = await make_public(client, their_headers, title='남의 것')
    await open_as_guest(client, their_headers, busy, 2)
    await open_tables(client, my_headers, busy, 1)
    await age(session, await open_tables(client, my_headers, old, 4), days=30)
    await open_tables(client, my_headers, down, 1)
    await client.put(f'{listing_url(down)}/publication', json={'version': None}, headers=my_headers)
    await open_tables(client, their_headers, theirs, 5)

    body = await stats(client, my_headers)

    assert body['recent_days'] == 7
    assert (body['total'], body['recent']) == (8, 4)
    assert rows(body) == [('이번 주', 3, 3), ('내림', 1, 1), ('지난달', 4, 0), ('아직 아무도', 0, 0)]
    assert rows(await stats(client, their_headers)) == [('남의 것', 5, 5)]


async def test_nothing_made_is_empty(client: AsyncClient, my_headers: dict):
    await create_scenario(client, my_headers, title='초안')

    assert await stats(client, my_headers) == {'recent_days': 7, 'total': 0, 'recent': 0, 'items': []}


async def test_needs_login(client: AsyncClient):
    response = await client.get(STATS_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_sums_every_row_but_lists_only_the_first():

    many = [(uuid.uuid4(), f'시나리오 {index}', 2, 1) for index in range(MAX_STATS_ITEMS + 5)]

    summary = summarize(many)

    assert (summary.total, summary.recent) == (2 * len(many), len(many))
    assert len(summary.items) == MAX_STATS_ITEMS
