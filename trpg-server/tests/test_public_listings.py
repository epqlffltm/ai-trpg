# trpg-server/tests/test_public_listings.py

"""
로그인하지 않은 사람이 공개 목록과 시나리오 소개를 읽는 것(#530)을 검증한다.

첫 화면(A1)은 로그인 전에도 전체 이용가 목록을 보인다. 전에는 GET /listings 와 GET /listings/{id} 가 401 이었다.
픽스처와 도우미는 tests/test_listings_api.py 의 것이다.

보는 것.
  - 토큰을 보내지 않으면 전체 이용가만 보인다. 성인용은 목록과 total 에서 빠지고, 소개는 404 다.
  - 로그인한 사람에게 보이는 것과 같은 모양이다. 거르는 조건과 쪽도 같다.
  - 토큰을 보냈는데 틀렸으면 401 이다. 로그인하지 않은 것으로 넘기지 않는다.
  - 성인 확인이 된 토큰에는 지금처럼 성인용도 보인다.
  - 등급을 가르는 함수는 로그인하지 않은 사람(None)에게 전체 이용가만 준다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.models import Rating
from app.assets.ratings import allowed_ratings
from tests import test_listings_api as listing_tests
from tests.test_listings_api import LISTINGS_URL, make_public

pytestmark = pytest.mark.usefixtures('clean_tables')

# 공개 정보 테스트의 픽스처를 그대로 쓴다. 나(제작자), 다른 사용자, 성인 인증을 한 나
my_headers = listing_tests.my_headers
their_headers = listing_tests.their_headers
my_adult_headers = listing_tests.my_adult_headers


def detail_url(scenario: dict) -> str:
    return f'{LISTINGS_URL}/{scenario["id"]}'


async def listed_ids(client: AsyncClient, headers: dict | None = None, **params) -> list[str]:
    response = await client.get(LISTINGS_URL, params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body['total'] == len(body['items'])
    return [item['scenario_id'] for item in body['items']]


def test_someone_not_logged_in_may_see_only_all_ages():
    assert allowed_ratings(None) == [Rating.ALL]


async def test_the_list_is_open_without_logging_in(client: AsyncClient, my_adult_headers: dict):
    all_ages = await make_public(client, my_adult_headers, title='전체 이용가')
    await make_public(client, my_adult_headers, title='성인용', rating='adult')

    # 성인용은 목록에도 total 에도 없다
    assert await listed_ids(client) == [all_ages['id']]


async def test_the_list_looks_the_same_as_for_someone_logged_in(client: AsyncClient, my_headers: dict):
    await make_public(client, my_headers, title='추격전', genres=['comedy'], recommended_players={'min': 2, 'max': 3})
    await make_public(client, my_headers, title='귀신', genres=['horror'])

    anonymous = await client.get(LISTINGS_URL)
    logged_in = await client.get(LISTINGS_URL, headers=my_headers)

    assert anonymous.json() == logged_in.json()
    # 거르는 조건과 쪽도 같다
    assert len(await listed_ids(client, genre='comedy', players=2)) == 1
    page = (await client.get(LISTINGS_URL, params={'limit': 1})).json()
    assert (len(page['items']), page['total']) == (1, 2)


async def test_the_introduction_is_open_without_logging_in(
    client: AsyncClient, my_headers: dict, my_adult_headers: dict
):
    all_ages = await make_public(client, my_headers)
    adult = await make_public(client, my_adult_headers, rating='adult')

    anonymous = await client.get(detail_url(all_ages))
    logged_in = await client.get(detail_url(all_ages), headers=my_headers)
    hidden = await client.get(detail_url(adult))

    assert anonymous.status_code == status.HTTP_200_OK
    assert anonymous.json() == logged_in.json()
    # 성인용은 있다는 것도 드러내지 않는다
    assert hidden.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize('authorization', ['Bearer not-a-token', 'Bearer x.y.z', 'Basic abc', ''])
async def test_a_token_that_was_sent_must_be_good(client: AsyncClient, my_headers: dict, authorization: str):
    scenario = await make_public(client, my_headers)

    for url in (LISTINGS_URL, detail_url(scenario)):
        response = await client.get(url, headers={'Authorization': authorization})
        # 보냈으면 검증한다. 틀린 토큰을 로그인하지 않은 것으로 넘기면 화면이 토큰을 갱신할 때를 모른다
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_an_adult_token_still_sees_adult(client: AsyncClient, my_adult_headers: dict, their_headers: dict):
    adult = await make_public(client, my_adult_headers, rating='adult')

    assert await listed_ids(client, my_adult_headers) == [adult['id']]
    assert await listed_ids(client, their_headers) == []
    assert (await client.get(detail_url(adult), headers=my_adult_headers)).status_code == status.HTTP_200_OK
