# trpg-server/tests/test_my_scenarios.py

"""
내 시나리오 목록의 쓰인 수와 관심 수, 공개 상태, 정렬(#1165)을 검증한다(GET /scenarios).

보는 것.
  - 줄마다 쓰인 수(start_count: 그 시나리오로 연 테이블의 모든 수)와 관심 수(heart_count: 공개 정보의 것)가 있다.
    공개 정보를 쓰지 않았으면 관심 수는 0 이다
  - 공개 상태: 공개한 시각(published_at, 공개하지 않았으면 null)과 링크 공개(unlisted)
  - 차례: 기본은 최근에 만든 것부터, updated 는 최근에 고친 것부터,
    started 는 쓰인 수가 많은 것부터(같으면 최근에 고친 것)
  - 모르는 차례는 422 다
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.listings.models import Listing
from app.main import API_PREFIX
from tests.test_listings_api import SCENARIOS_URL, create_scenario, listing_url, make_public, publish_version
from tests.test_listings_api import my_headers as my_headers  # noqa: F401  (픽스처)

pytestmark = pytest.mark.usefixtures('clean_tables')

TABLES_URL = f'{API_PREFIX}/tables'


async def open_table(client: AsyncClient, headers: dict, scenario: dict, version: int = 1) -> None:
    """그 시나리오의 판으로 테이블을 하나 연다."""
    body = {'scenario_id': scenario['id'], 'version': version, 'capacity': 2}
    response = await client.post(TABLES_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text


async def rows(client: AsyncClient, headers: dict, **params) -> list[dict]:
    response = await client.get(SCENARIOS_URL, params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['items']


def counts(items: list[dict]) -> list[tuple[str, int, int]]:
    return [(item['title'], item['start_count'], item['heart_count']) for item in items]


async def test_my_list_carries_the_counts_and_the_publication(
    client: AsyncClient, my_headers: dict, session: AsyncSession
):
    draft = await create_scenario(client, my_headers, title='초안')
    played = await make_public(client, my_headers, title='공개')
    await open_table(client, my_headers, played)
    await open_table(client, my_headers, played)
    await session.execute(update(Listing).where(Listing.scenario_id == played['id']).values(heart_count=5))
    await session.commit()

    items = await rows(client, my_headers)

    assert counts(items) == [('공개', 2, 5), ('초안', 0, 0)]
    published, unpublished = items
    assert (published['published_at'] is not None, published['unlisted']) == (True, False)
    assert (unpublished['published_at'], unpublished['unlisted']) == (None, False)
    assert unpublished['id'] == draft['id']


async def test_a_private_table_counts_too(client: AsyncClient, my_headers: dict):
    scenario = await create_scenario(client, my_headers, title='나만')
    number = await publish_version(client, my_headers, scenario)
    await open_table(client, my_headers, scenario, number)

    assert counts(await rows(client, my_headers)) == [('나만', 1, 0)]


async def test_an_unlisted_scenario_says_so(client: AsyncClient, my_headers: dict):
    scenario = await make_public(client, my_headers, title='링크')
    await client.patch(listing_url(scenario), json={'unlisted': True}, headers=my_headers)

    (item,) = await rows(client, my_headers)

    assert item['unlisted'] is True


async def test_the_list_sorts_by_creation_edit_or_starts(client: AsyncClient, my_headers: dict):
    first = await make_public(client, my_headers, title='하나')
    await make_public(client, my_headers, title='둘')
    busy = await make_public(client, my_headers, title='셋')
    for _ in range(3):
        await open_table(client, my_headers, busy)
    await open_table(client, my_headers, first)
    await client.patch(f'{SCENARIOS_URL}/{first["id"]}', json={'description': '고침'}, headers=my_headers)

    created = [item['title'] for item in await rows(client, my_headers)]
    edited = [item['title'] for item in await rows(client, my_headers, sort='updated')]
    started = [item['title'] for item in await rows(client, my_headers, sort='started')]

    assert created == ['셋', '둘', '하나']
    assert edited == ['하나', '셋', '둘']
    assert started == ['셋', '하나', '둘']


async def test_an_unknown_order_is_refused(client: AsyncClient, my_headers: dict):
    response = await client.get(SCENARIOS_URL, params={'sort': 'popular'}, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
