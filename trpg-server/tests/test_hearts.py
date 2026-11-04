# trpg-server/tests/test_hearts.py

"""
시나리오의 관심(하트, #989)을 검증한다. 실제 DB(game_test)에서 돈다.

  - 두면 내가 둔 것으로 보이고 관심의 수가 하나 는다. 두 번 두거나 두 번 거둬도 수가 어긋나지 않는다
  - 공개 목록과 소개에 관심의 수가 실린다
  - 둘 수 있는 것은 공개 중이고 볼 수 있는 것이다(아니면 404). 거두는 것은 공개를 내린 뒤에도 된다
  - 내 관심 작품은 최근에 둔 것부터, 지금 볼 수 있는 것만이다
  - 로그인해야 한다. 탈퇴하면 그 사람의 관심을 거두고 수도 뺀다
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from app.main import API_PREFIX
from tests import test_listings_api as listing_tests
from tests.test_listings_api import LISTINGS_URL, listing_url, make_public
from tests.test_withdrawal import notify

pytestmark = pytest.mark.usefixtures('clean_tables')

my_headers = listing_tests.my_headers
their_headers = listing_tests.their_headers
my_adult_headers = listing_tests.my_adult_headers
adult_headers = listing_tests.adult_headers

HEARTED_URL = f'{API_PREFIX}/listings/hearted'


def heart_url(scenario: dict) -> str:
    return f'{LISTINGS_URL}/{scenario["id"]}/heart'


async def count_in_list(client: AsyncClient, scenario: dict) -> int:
    items = (await client.get(LISTINGS_URL)).json()['items']
    return next(item['heart_count'] for item in items if item['scenario_id'] == scenario['id'])


async def test_hearts_count_once_per_person(client: AsyncClient, my_headers: dict, their_headers: dict):
    scenario = await make_public(client, my_headers, title='추격전')

    first = await client.put(heart_url(scenario), headers=their_headers)
    again = await client.put(heart_url(scenario), headers=their_headers)
    mine = await client.put(heart_url(scenario), headers=my_headers)

    assert first.status_code == status.HTTP_200_OK, first.text
    assert first.json() == {'hearted': True, 'heart_count': 1}
    assert again.json() == {'hearted': True, 'heart_count': 1}
    assert mine.json() == {'hearted': True, 'heart_count': 2}
    # 목록과 소개에 실린다
    assert await count_in_list(client, scenario) == 2
    assert (await client.get(f'{LISTINGS_URL}/{scenario["id"]}')).json()['heart_count'] == 2

    taken = await client.delete(heart_url(scenario), headers=their_headers)
    taken_again = await client.delete(heart_url(scenario), headers=their_headers)
    read = await client.get(heart_url(scenario), headers=their_headers)

    assert taken.json() == taken_again.json() == read.json() == {'hearted': False, 'heart_count': 1}
    assert (await client.get(heart_url(scenario), headers=my_headers)).json() == {'hearted': True, 'heart_count': 1}


async def test_only_visible_scenarios_take_hearts(
    client: AsyncClient, my_headers: dict, my_adult_headers: dict, their_headers: dict, adult_headers: dict
):
    night = await make_public(client, my_adult_headers, title='밤', rating='adult')
    later = await make_public(client, my_headers, title='내릴 것')
    await client.put(heart_url(later), headers=their_headers)
    await client.put(f'{listing_url(later)}/publication', json={'version': None}, headers=my_headers)

    # 볼 수 없는 등급과 공개를 내린 것은 없는 것이다. 성인은 둔다
    assert (await client.put(heart_url(night), headers=their_headers)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.put(heart_url(later), headers=adult_headers)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(heart_url(later), headers=their_headers)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.put(heart_url(night), headers=adult_headers)).json()['heart_count'] == 1
    # 공개를 내린 뒤에도 거둔다
    assert (await client.delete(heart_url(later), headers=their_headers)).json() == {'hearted': False, 'heart_count': 0}


async def test_my_hearted_list(client: AsyncClient, my_headers: dict, their_headers: dict):
    first = await make_public(client, my_headers, title='먼저')
    second = await make_public(client, my_headers, title='나중')
    gone = await make_public(client, my_headers, title='내림')
    for scenario in (first, gone, second):
        await client.put(heart_url(scenario), headers=their_headers)
    await client.put(f'{listing_url(gone)}/publication', json={'version': None}, headers=my_headers)

    page = (await client.get(HEARTED_URL, headers=their_headers)).json()
    mine = (await client.get(HEARTED_URL, headers=my_headers)).json()

    # 최근에 둔 것부터, 지금 볼 수 있는 것만이다
    assert ([item['title'] for item in page['items']], page['total']) == (['나중', '먼저'], 2)
    assert mine == {'items': [], 'total': 0}
    limited = (await client.get(HEARTED_URL, params={'limit': 1, 'offset': 1}, headers=their_headers)).json()
    assert [item['title'] for item in limited['items']] == ['먼저']


async def test_hearts_need_login(client: AsyncClient, my_headers: dict):
    scenario = await make_public(client, my_headers)

    for method in ('GET', 'PUT', 'DELETE'):
        response = await client.request(method, heart_url(scenario))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert (await client.get(HEARTED_URL)).status_code == status.HTTP_401_UNAUTHORIZED


async def test_withdrawal_takes_back_the_hearts(client: AsyncClient, my_headers: dict, their_headers: dict):
    scenario = await make_public(client, my_headers)
    await client.put(heart_url(scenario), headers=their_headers)
    await client.put(heart_url(scenario), headers=my_headers)

    response = await notify(client, listing_tests.SOMEONE_ELSE)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert (await client.get(heart_url(scenario), headers=my_headers)).json() == {'hearted': True, 'heart_count': 1}
