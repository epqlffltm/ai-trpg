# trpg-server/tests/test_banners.py

"""
홍보 배너(#994)를 검증한다. 운영자가 공개 중인 시나리오를 걸고, 누구나 지금 걸린 것을 차례대로 본다.

  - 공개를 내렸거나 지운 시나리오, 링크로만 여는 것, 볼 수 없는 등급, 기간 밖의 배너는 보이지 않는다
  - 공개 목록처럼 보는 사람의 설정(성인 작품 숨김, 성향)으로 거른다
  - 운영자의 주소는 운영자가 아니면 404 다
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient

from app.main import API_PREFIX
from tests import test_listings_api as listing_tests
from tests.test_listings_api import SCENARIOS_URL, create_scenario, listing_url, make_public, write_page

pytestmark = pytest.mark.usefixtures('clean_tables')

# 공개 정보 테스트의 픽스처를 그대로 쓴다
my_headers = listing_tests.my_headers
their_headers = listing_tests.their_headers
my_adult_headers = listing_tests.my_adult_headers
adult_headers = listing_tests.adult_headers
operator_headers = listing_tests.operator_headers

BANNERS_URL = f'{API_PREFIX}/banners'
ADMIN_URL = f'{API_PREFIX}/admin/banners'


def iso(moment: datetime) -> str:
    return moment.isoformat()


async def hang(client: AsyncClient, headers: dict, scenario: dict, **fields) -> dict:
    """배너를 건다."""
    response = await client.post(ADMIN_URL, json={'scenario_id': scenario['id'], **fields}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def shown(client: AsyncClient, headers: dict | None = None, params: dict | None = None) -> list[str]:
    """지금 보이는 배너의 시나리오 제목, 차례대로."""
    response = await client.get(BANNERS_URL, params=params or {}, headers=headers or {})
    assert response.status_code == status.HTTP_200_OK, response.text
    return [item['listing']['title'] for item in response.json()['items']]


async def test_banners_are_shown_in_order_to_anyone(client: AsyncClient, my_headers: dict, operator_headers: dict):
    second = await make_public(client, my_headers, title='둘째')
    first = await make_public(client, my_headers, title='첫째')
    await hang(client, operator_headers, second, position=2)
    await hang(client, operator_headers, first, position=1)

    # 로그인하지 않아도 본다. 시나리오의 공개 정보 그대로다
    assert await shown(client) == ['첫째', '둘째']
    item = (await client.get(BANNERS_URL)).json()['items'][0]
    assert item['listing']['scenario_id'] == first['id']


async def test_only_published_scenarios_can_be_hung(client: AsyncClient, my_headers: dict, operator_headers: dict):
    draft = await create_scenario(client, my_headers)
    missing = '00000000-0000-4000-8000-000000000000'

    unpublished = await client.post(ADMIN_URL, json={'scenario_id': draft['id']}, headers=operator_headers)
    unknown = await client.post(ADMIN_URL, json={'scenario_id': missing}, headers=operator_headers)

    assert unpublished.status_code == unknown.status_code == status.HTTP_409_CONFLICT
    assert unpublished.json()['code'] == 'not_published'


async def test_a_scenario_taken_down_disappears_and_comes_back(
    client: AsyncClient, my_headers: dict, operator_headers: dict
):
    scenario = await make_public(client, my_headers, title='내렸다 올림')
    await hang(client, operator_headers, scenario)

    await client.put(f'{listing_url(scenario)}/publication', json={'version': None}, headers=my_headers)
    hidden = await shown(client)
    listed = (await client.get(ADMIN_URL, headers=operator_headers)).json()
    await client.put(f'{listing_url(scenario)}/publication', json={'version': 1}, headers=my_headers)

    assert hidden == []
    # 운영자에게는 남아 있고, 지금 보이지 않는다고 나온다
    assert [(item['title'], item['shown']) for item in listed] == [('내렸다 올림', False)]
    assert await shown(client) == ['내렸다 올림']


async def test_a_deleted_scenario_disappears(client: AsyncClient, my_headers: dict, operator_headers: dict):
    scenario = await make_public(client, my_headers, title='지움')
    await hang(client, operator_headers, scenario)

    await client.delete(f'{SCENARIOS_URL}/{scenario["id"]}', headers=my_headers)

    assert await shown(client) == []


async def test_an_adult_banner_is_shown_only_to_adults(
    client: AsyncClient, my_adult_headers: dict, adult_headers: dict, their_headers: dict, operator_headers: dict
):
    scenario = await make_public(client, my_adult_headers, title='밤', rating='adult')
    await hang(client, operator_headers, scenario)

    assert (await shown(client), await shown(client, their_headers)) == ([], [])
    assert await shown(client, adult_headers) == ['밤']


async def test_an_unlisted_scenario_is_not_shown(client: AsyncClient, my_headers: dict, operator_headers: dict):
    scenario = await make_public(client, my_headers, title='링크만')
    await hang(client, operator_headers, scenario)

    await write_page(client, my_headers, scenario, unlisted=True)
    listed = (await client.get(ADMIN_URL, headers=operator_headers)).json()

    # 링크로만 여는 시나리오(#993)는 공개 목록처럼 배너에도 나오지 않는다. 운영자에게는 보이지 않는다고 나온다
    assert await shown(client) == []
    assert [(item['title'], item['shown']) for item in listed] == [('링크만', False)]


async def test_banners_follow_the_viewer_preferences(
    client: AsyncClient, my_adult_headers: dict, adult_headers: dict, operator_headers: dict
):
    night = await make_public(client, my_adult_headers, title='밤', rating='adult', tags=['남성향'])
    day = await make_public(client, my_adult_headers, title='낮', tags=['여성향'])
    await hang(client, operator_headers, night, position=1)
    await hang(client, operator_headers, day, position=2)

    # 공개 목록처럼 성인 작품 숨김(#986)과 성향(#987)으로 거른다
    assert await shown(client, adult_headers) == ['밤', '낮']
    assert await shown(client, adult_headers, {'hide_adult': 'true'}) == ['낮']
    assert await shown(client, adult_headers, {'orientation': 'male'}) == ['밤']


async def test_banners_show_only_within_their_period(client: AsyncClient, my_headers: dict, operator_headers: dict):
    now = datetime.now(UTC)
    later = await make_public(client, my_headers, title='나중')
    over = await make_public(client, my_headers, title='지남')
    now_on = await make_public(client, my_headers, title='지금')
    await hang(client, operator_headers, later, starts_at=iso(now + timedelta(days=1)))
    await hang(
        client, operator_headers, over, starts_at=iso(now - timedelta(days=2)), ends_at=iso(now - timedelta(days=1))
    )
    await hang(client, operator_headers, now_on, ends_at=iso(now + timedelta(days=1)))

    assert await shown(client) == ['지금']


async def test_the_operator_changes_order_and_period_and_takes_it_down(
    client: AsyncClient, my_headers: dict, operator_headers: dict
):
    a = await make_public(client, my_headers, title='가')
    b = await make_public(client, my_headers, title='나')
    first = await hang(client, operator_headers, a, position=1)
    await hang(client, operator_headers, b, position=2)

    moved = await client.patch(f'{ADMIN_URL}/{first["id"]}', json={'position': 3}, headers=operator_headers)
    order = await shown(client)
    ended = await client.patch(
        f'{ADMIN_URL}/{first["id"]}',
        json={'ends_at': iso(datetime.now(UTC) - timedelta(seconds=1))},
        headers=operator_headers,
    )
    cleared = await client.patch(f'{ADMIN_URL}/{first["id"]}', json={'position': None}, headers=operator_headers)
    removed = await client.delete(f'{ADMIN_URL}/{first["id"]}', headers=operator_headers)
    again = await client.delete(f'{ADMIN_URL}/{first["id"]}', headers=operator_headers)

    assert moved.status_code == status.HTTP_200_OK and order == ['나', '가']
    # 끝이 시작보다 앞이면 받지 않는다
    assert (ended.status_code, cleared.status_code) == (status.HTTP_422_UNPROCESSABLE_CONTENT,) * 2
    assert (removed.status_code, again.status_code) == (status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND)
    assert await shown(client) == ['나']


@pytest.mark.parametrize(
    'body',
    [
        {'position': -1},
        {'position': 1000},
        {'starts_at': '2026-11-02T00:00:00Z', 'ends_at': '2026-11-01T00:00:00Z'},
        {'starts_at': '2026-11-02T00:00:00'},
        {'link': 'x'},
    ],
)
async def test_rejects_a_bad_banner(client: AsyncClient, my_headers: dict, operator_headers: dict, body: dict):
    scenario = await make_public(client, my_headers)

    response = await client.post(ADMIN_URL, json={'scenario_id': scenario['id'], **body}, headers=operator_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_admin_addresses_are_404_for_others(client: AsyncClient, my_headers: dict):
    scenario = await make_public(client, my_headers)

    listing = await client.get(ADMIN_URL, headers=my_headers)
    created = await client.post(ADMIN_URL, json={'scenario_id': scenario['id']}, headers=my_headers)
    anonymous = await client.get(ADMIN_URL)

    assert (listing.status_code, created.status_code) == (status.HTTP_404_NOT_FOUND,) * 2
    assert anonymous.status_code == status.HTTP_401_UNAUTHORIZED
