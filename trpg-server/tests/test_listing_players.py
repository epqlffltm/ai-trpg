# trpg-server/tests/test_listing_players.py

"""
공개 목록을 함께 할 인원으로 거르는 것(#428, GET /listings?players=N)을 검증한다.

추천 인원은 카드에 보이기만 했다. 화면 목록(B1)의 "인원으로 찾기"를 할 값이 서버에 없었다.
픽스처와 도우미는 tests/test_listings_api.py 의 것이다.

보는 것.
  - N 이 추천 인원의 최소와 최대 사이(양 끝 포함)에 드는 시나리오만 나온다. total 도 같다.
  - 장르, 태그와 함께 걸면 모두 맞는 것만 나온다.
  - 거르는 값은 공개 중인 판의 추천 인원을 따른다. 초안을 고치기만 해서는 바뀌지 않는다.
  - 1 보다 작거나 테이블의 정원보다 큰 수는 422 다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.models import TABLE_MAX_PLAYERS
from tests import test_listings_api as listing_tests
from tests.test_listings_api import LISTINGS_URL, SCENARIOS_URL, listing_url, make_public, publish_version

pytestmark = pytest.mark.usefixtures('clean_tables')

# 공개 정보 테스트의 픽스처를 그대로 쓴다
my_headers = listing_tests.my_headers


def players(low: int, high: int) -> dict:
    return {'recommended_players': {'min': low, 'max': high}}


async def ids(client: AsyncClient, headers: dict, **params) -> set[str]:
    response = await client.get(LISTINGS_URL, params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body['total'] == len(body['items'])
    return {item['scenario_id'] for item in body['items']}


async def test_only_scenarios_that_fit_the_party_are_listed(client: AsyncClient, my_headers: dict):
    solo = await make_public(client, my_headers, title='혼자', **players(1, 1))
    pair = await make_public(client, my_headers, title='둘에서 셋', **players(2, 3))
    party = await make_public(client, my_headers, title='셋에서 넷', **players(3, 4))

    assert await ids(client, my_headers, players=1) == {solo['id']}
    assert await ids(client, my_headers, players=2) == {pair['id']}
    # 양 끝을 포함한다
    assert await ids(client, my_headers, players=3) == {pair['id'], party['id']}
    assert await ids(client, my_headers, players=4) == {party['id']}
    assert await ids(client, my_headers) == {solo['id'], pair['id'], party['id']}


async def test_it_combines_with_genre_and_tag(client: AsyncClient, my_headers: dict):
    chase = await make_public(client, my_headers, title='추격전', genre='comedy', tags=['바이크'], **players(2, 4))
    await make_public(client, my_headers, title='혼자 웃기', genre='comedy', tags=['바이크'], **players(1, 1))
    await make_public(client, my_headers, title='귀신', genre='horror', tags=['바이크'], **players(2, 4))
    await make_public(client, my_headers, title='검객', genre='comedy', tags=['복수'], **players(2, 4))

    assert await ids(client, my_headers, players=2, genre='comedy', tag='바이크') == {chase['id']}


async def test_it_follows_the_public_version(client: AsyncClient, my_headers: dict):
    scenario = await make_public(client, my_headers, **players(1, 2))
    url = f'{SCENARIOS_URL}/{scenario["id"]}'
    await client.patch(url, json=players(3, 4), headers=my_headers)

    # 초안만 고쳤다. 공개 중인 판은 그대로다
    assert await ids(client, my_headers, players=4) == set()

    number = await publish_version(client, my_headers, scenario)
    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': number}, headers=my_headers)
    assert response.status_code == status.HTTP_200_OK, response.text

    assert await ids(client, my_headers, players=4) == {scenario['id']}
    assert await ids(client, my_headers, players=1) == set()


@pytest.mark.parametrize('count', [0, -1, TABLE_MAX_PLAYERS + 1, 'two'])
async def test_rejects_a_count_no_table_can_hold(client: AsyncClient, my_headers: dict, count):
    response = await client.get(LISTINGS_URL, params={'players': count}, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
