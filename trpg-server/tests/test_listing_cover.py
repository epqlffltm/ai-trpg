# trpg-server/tests/test_listing_cover.py

"""
시나리오의 표지 그림(#1164)을 검증한다. asset 서버는 가짜다(tests/asset_server.py).

보는 것.
  - 내가 올린 그림을 소개 페이지의 표지로 붙이고, null 로 떼고, 보내지 않으면 그대로다
  - 남의 그림이나 없는 그림은 422 다
  - 공개 목록과 상세에 cover_image_id 가 실리고, 로그인하지 않아도 표지의 바이트를 받는다
  - 표지로 쓰는 그림은 지우지 못한다(portrait_in_use)
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from app.main import API_PREFIX
from tests.asset_server import FakeAsset
from tests.test_listings_api import NO_SUCH_ID, listing_url, make_public, write_page
from tests.test_listings_api import create_scenario as create_scenario
from tests.test_listings_api import my_headers as my_headers  # noqa: F401  (픽스처)
from tests.test_listings_api import their_headers as their_headers  # noqa: F401  (픽스처)

pytestmark = pytest.mark.usefixtures('clean_tables')

PORTRAITS_URL = f'{API_PREFIX}/portraits'
LISTINGS_URL = f'{API_PREFIX}/listings'
COVER = b'\x89PNG cover'


@pytest.fixture
def asset(app) -> FakeAsset:
    fake = FakeAsset()
    app.state.asset = fake
    return fake


async def upload(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(PORTRAITS_URL, content=COVER, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


async def patch_page(client: AsyncClient, headers: dict[str, str], scenario: dict, **fields):
    return await client.patch(listing_url(scenario), json=fields, headers=headers)


@pytest.mark.usefixtures('asset')
async def test_puts_on_keeps_and_takes_off_the_cover(client: AsyncClient, my_headers: dict[str, str]):
    image_id = await upload(client, my_headers)
    scenario = await create_scenario(client, my_headers)
    await write_page(client, my_headers, scenario)

    put_on = await patch_page(client, my_headers, scenario, cover_image_id=image_id)
    kept = await patch_page(client, my_headers, scenario, tagline='표지는 그대로')
    taken_off = await patch_page(client, my_headers, scenario, cover_image_id=None)

    assert put_on.status_code == status.HTTP_200_OK, put_on.text
    assert put_on.json()['cover_image_id'] == image_id
    assert kept.json()['cover_image_id'] == image_id
    assert taken_off.json()['cover_image_id'] is None


@pytest.mark.usefixtures('asset')
async def test_the_first_write_can_carry_a_cover(client: AsyncClient, my_headers: dict[str, str]):
    image_id = await upload(client, my_headers)
    scenario = await create_scenario(client, my_headers)

    response = await patch_page(client, my_headers, scenario, genre='sf', cover_image_id=image_id)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['cover_image_id'] == image_id


@pytest.mark.usefixtures('asset')
async def test_someone_elses_or_a_missing_picture_is_refused(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await upload(client, their_headers)
    scenario = await create_scenario(client, my_headers)
    await write_page(client, my_headers, scenario)

    foreign = await patch_page(client, my_headers, scenario, cover_image_id=theirs)
    missing = await patch_page(client, my_headers, scenario, cover_image_id=NO_SUCH_ID)
    page = await client.get(listing_url(scenario), headers=my_headers)

    assert foreign.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert missing.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert page.json()['cover_image_id'] is None


@pytest.mark.usefixtures('asset')
async def test_a_public_scenario_shows_its_cover_without_a_login(client: AsyncClient, my_headers: dict[str, str]):
    image_id = await upload(client, my_headers)
    scenario = await make_public(client, my_headers)
    await patch_page(client, my_headers, scenario, cover_image_id=image_id)

    listed = (await client.get(LISTINGS_URL)).json()['items']
    detail = (await client.get(f'{LISTINGS_URL}/{scenario["id"]}')).json()
    image = await client.get(f'{LISTINGS_URL}/{scenario["id"]}/portraits/{image_id}/image')

    assert [item['cover_image_id'] for item in listed] == [image_id]
    assert detail['cover_image_id'] == image_id
    assert (image.status_code, image.content) == (status.HTTP_200_OK, COVER)


@pytest.mark.usefixtures('asset')
async def test_a_cover_is_not_served_for_a_scenario_that_is_not_public(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    image_id = await upload(client, my_headers)
    scenario = await create_scenario(client, my_headers)
    await write_page(client, my_headers, scenario)
    await patch_page(client, my_headers, scenario, cover_image_id=image_id)

    response = await client.get(f'{LISTINGS_URL}/{scenario["id"]}/portraits/{image_id}/image', headers=their_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('asset')
async def test_a_cover_cannot_be_deleted(client: AsyncClient, my_headers: dict[str, str]):
    image_id = await upload(client, my_headers)
    scenario = await create_scenario(client, my_headers, title='표지의 시나리오')
    await write_page(client, my_headers, scenario)
    await patch_page(client, my_headers, scenario, cover_image_id=image_id)

    refused = await client.delete(f'{PORTRAITS_URL}/{image_id}', headers=my_headers)
    await patch_page(client, my_headers, scenario, cover_image_id=None)
    deleted = await client.delete(f'{PORTRAITS_URL}/{image_id}', headers=my_headers)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['code'] == 'portrait_in_use'
    assert refused.json()['scenarios'] == [{'id': scenario['id'], 'title': '표지의 시나리오'}]
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
