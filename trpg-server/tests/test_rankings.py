# trpg-server/tests/test_rankings.py

"""
시나리오의 랭킹(app/rankings/, #985)을 검증한다. 실제 DB(game_test)에서 돈다.

  - 최근 7일에 연 테이블이 많은 것부터다. 같으면 모든 수가 많은 것부터다. 7일보다 앞의 테이블은 최근의 수에 들지 않는다
  - 최근의 수가 0 인 것, 공개를 내린 것, 링크로만 여는 것(#993), 볼 수 없는 등급은 빠진다
  - 보는 사람의 설정(hide_adult, orientation)으로 거르고, limit 만큼만 준다
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.tables.models import GameTable
from tests import test_listings_api as listing_tests
from tests.test_listings_api import listing_url, make_public, write_page

pytestmark = pytest.mark.usefixtures('clean_tables')

my_headers = listing_tests.my_headers
my_adult_headers = listing_tests.my_adult_headers
adult_headers = listing_tests.adult_headers

RANKING_URL = f'{API_PREFIX}/rankings/scenarios'
TABLES_URL = f'{API_PREFIX}/tables'


async def open_tables(client: AsyncClient, headers: dict, scenario: dict, count: int) -> list[str]:
    """그 시나리오의 1번 판으로 테이블을 count 개 연다. 테이블의 id 들이다."""
    ids = []
    for _ in range(count):
        body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
        response = await client.post(TABLES_URL, json=body, headers=headers)
        assert response.status_code == status.HTTP_201_CREATED, response.text
        ids.append(response.json()['id'])
    return ids


async def age(session: AsyncSession, table_ids: list[str], days: int) -> None:
    """테이블을 days 일 전에 연 것으로 바꾼다."""
    opened = datetime.now(UTC) - timedelta(days=days)
    ids = [uuid.UUID(table_id) for table_id in table_ids]
    await session.execute(update(GameTable).where(GameTable.id.in_(ids)).values(created_at=opened))
    await session.commit()


async def ranked(client: AsyncClient, headers: dict | None = None, **params) -> list[tuple[int, str, int]]:
    response = await client.get(RANKING_URL, params=params, headers=headers or {})
    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['recent_days'] == 7
    return [(item['rank'], item['listing']['title'], item['starts']) for item in response.json()['items']]


async def test_scenarios_are_ranked_by_tables_opened_this_week(
    client: AsyncClient, session: AsyncSession, my_headers: dict, my_adult_headers: dict, adult_headers: dict
):
    first = await make_public(client, my_headers, title='첫째', tags=['남성향'])
    second = await make_public(client, my_headers, title='둘째', tags=['여성향'])
    tie = await make_public(client, my_headers, title='같은 수')
    old = await make_public(client, my_headers, title='지난달만')
    night = await make_public(client, my_adult_headers, title='밤', rating='adult')
    hidden = await make_public(client, my_headers, title='링크만')
    down = await make_public(client, my_headers, title='내림')
    await open_tables(client, my_headers, first, 3)
    await open_tables(client, my_headers, second, 2)
    await age(session, await open_tables(client, my_headers, second, 1), days=30)
    await open_tables(client, my_headers, tie, 2)
    await age(session, await open_tables(client, my_headers, old, 4), days=8)
    await open_tables(client, my_adult_headers, night, 4)
    await open_tables(client, my_headers, hidden, 5)
    await write_page(client, my_headers, hidden, unlisted=True)
    await open_tables(client, my_headers, down, 5)
    await client.put(f'{listing_url(down)}/publication', json={'version': None}, headers=my_headers)

    # 최근의 수, 같으면 모든 수가 많은 것부터다. 지난 것만 있는 것, 링크 공개, 공개를 내린 것은 빠진다
    assert await ranked(client) == [(1, '첫째', 3), (2, '둘째', 2), (3, '같은 수', 2)]
    # 성인용은 볼 수 있는 사람에게만 나온다. 보는 사람의 설정(#986, #987)과 개수
    assert await ranked(client, adult_headers) == [(1, '밤', 4), (2, '첫째', 3), (3, '둘째', 2), (4, '같은 수', 2)]
    assert await ranked(client, adult_headers, hide_adult='true', limit=2) == [(1, '첫째', 3), (2, '둘째', 2)]
    assert await ranked(client, adult_headers, orientation='female') == [(1, '둘째', 2)]


async def test_nothing_opened_is_an_empty_ranking(client: AsyncClient, my_headers: dict):
    await make_public(client, my_headers, title='아무도 안 함')

    assert await ranked(client) == []


@pytest.mark.parametrize('params', [{'limit': 0}, {'limit': 21}, {'orientation': 'both'}])
async def test_rejects_a_bad_query(client: AsyncClient, params: dict):
    response = await client.get(RANKING_URL, params=params)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
