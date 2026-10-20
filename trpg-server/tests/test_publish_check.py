# trpg-server/tests/test_publish_check.py

"""
게시하기 전에 막히는 이유를 미리 보는 것(#428, GET /scenarios/{id}/publish-check)을 검증한다.

전에는 게시해 보고 409 의 problems 를 받아야 알았다. 막히지 않으면 그대로 판이 생겨 버렸다.
픽스처와 도우미는 tests/test_listings_api.py 의 것이다.

보는 것.
  - 갖추었으면 ready 가 참이고 problems 가 비어 있다. 판은 생기지 않는다.
  - 갖추지 못했으면 게시가 409 로 돌려주는 것과 같은 이유들이다. 판은 생기지 않는다.
  - 남의 것과 없는 것은 404, 성인용 초안을 볼 수 없는 토큰은 403 이다. 게시와 같다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from tests import test_listings_api as listing_tests
from tests.narration_model import with_model
from tests.test_listings_api import NO_SUCH_ID, SCENARIOS_URL, create_scenario

pytestmark = pytest.mark.usefixtures('clean_tables')

# 공개 정보 테스트의 픽스처를 그대로 쓴다. 나(제작자), 다른 사용자, 성인 인증을 한 나
my_headers = listing_tests.my_headers
their_headers = listing_tests.their_headers
my_adult_headers = listing_tests.my_adult_headers


def check_url(scenario_id: str) -> str:
    return f'{SCENARIOS_URL}/{scenario_id}/publish-check'


async def versions_of(client: AsyncClient, headers: dict, scenario: dict) -> list[dict]:
    response = await client.get(f'{SCENARIOS_URL}/{scenario["id"]}/versions', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_a_ready_scenario_is_ready_and_nothing_is_published(client: AsyncClient, my_headers: dict):
    scenario = await create_scenario(client, my_headers)

    response = await client.get(check_url(scenario['id']), headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'ready': True, 'problems': []}
    assert await versions_of(client, my_headers, scenario) == []


async def test_the_problems_are_the_ones_publishing_would_give(client: AsyncClient, my_headers: dict):
    # 룰북도 스타팅도 기본 시트도 없는 초안
    created = await client.post(SCENARIOS_URL, json=with_model({'title': '초안'}), headers=my_headers)
    scenario = created.json()

    checked = await client.get(check_url(scenario['id']), headers=my_headers)
    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=my_headers)

    assert published.status_code == status.HTTP_409_CONFLICT
    assert checked.json() == {'ready': False, 'problems': published.json()['problems']}
    assert 'rulebook_missing' in checked.json()['problems']
    assert await versions_of(client, my_headers, scenario) == []


@pytest.mark.parametrize('scenario_id', [NO_SUCH_ID, 'theirs'])
async def test_only_ones_own_scenario_can_be_checked(
    client: AsyncClient, my_headers: dict, their_headers: dict, scenario_id: str
):
    if scenario_id == 'theirs':
        scenario_id = (await create_scenario(client, their_headers))['id']

    response = await client.get(check_url(scenario_id), headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_it_requires_login(client: AsyncClient):
    assert (await client.get(check_url(NO_SUCH_ID))).status_code == status.HTTP_401_UNAUTHORIZED


async def test_an_adult_draft_needs_an_adult_token_like_publishing(
    client: AsyncClient, my_headers: dict, my_adult_headers: dict
):
    scenario = await create_scenario(client, my_adult_headers, rating='adult')

    checked = await client.get(check_url(scenario['id']), headers=my_headers)
    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=my_headers)
    allowed = await client.get(check_url(scenario['id']), headers=my_adult_headers)

    assert checked.status_code == published.status_code == status.HTTP_403_FORBIDDEN
    assert allowed.json() == {'ready': True, 'problems': []}
