# trpg-server/tests/test_portrait_listings.py

"""
고르기 전에 보이는 프리젠의 캐릭터 그림(#983)을 검증한다. asset 서버는 가짜다(tests/asset_server.py).

보는 것.
  - 공개된 시나리오의 프리젠에 portrait_id 가 실리고, 로그인하지 않아도 전체 이용가의 그림을 받는다
  - 공개 중인 판에 없는 그림, 공개하지 않은 시나리오의 그림은 404 다
  - 테이블의 고를 수 있는 프리젠(TableDetail.pregens)에도 portrait_id 가 실린다
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from app.main import API_PREFIX
from tests.asset_server import FakeAsset
from tests.sheets import SHEET
from tests.test_listings_api import create_scenario, make_public, publish_version
from tests.test_listings_api import my_headers as my_headers  # noqa: F401  (픽스처)
from tests.test_listings_api import their_headers as their_headers  # noqa: F401  (픽스처)

pytestmark = pytest.mark.usefixtures('clean_tables')

PORTRAITS_URL = f'{API_PREFIX}/portraits'
LISTINGS_URL = f'{API_PREFIX}/listings'
TABLES_URL = f'{API_PREFIX}/tables'
FACE = b'\x89PNG elf face'


@pytest.fixture
def asset(app) -> FakeAsset:
    fake = FakeAsset()
    app.state.asset = fake
    return fake


async def upload(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(PORTRAITS_URL, content=FACE, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


def pregens_with(image_id: str) -> list[dict]:
    return [{'name': '엘프', 'sheet': SHEET, 'image_id': image_id}, {'name': '영애', 'sheet': SHEET}]


def image_url(scenario: dict, image_id: str) -> str:
    return f'{LISTINGS_URL}/{scenario["id"]}/portraits/{image_id}/image'


@pytest.mark.usefixtures('asset')
async def test_a_public_scenario_shows_its_pregen_portraits_without_a_login(
    client: AsyncClient, my_headers: dict[str, str]
):
    image_id = await upload(client, my_headers)
    other = await upload(client, my_headers)
    scenario = await make_public(client, my_headers, pregens=pregens_with(image_id))

    detail = (await client.get(f'{LISTINGS_URL}/{scenario["id"]}')).json()
    anonymous = await client.get(image_url(scenario, image_id))
    not_in_the_version = await client.get(image_url(scenario, other))

    assert [pregen['portrait_id'] for pregen in detail['pregens']] == [image_id, None]
    assert (anonymous.status_code, anonymous.content) == (status.HTTP_200_OK, FACE)
    assert (not_in_the_version.status_code, not_in_the_version.json()['code']) == (
        status.HTTP_404_NOT_FOUND,
        'portrait_not_found',
    )


@pytest.mark.usefixtures('asset')
async def test_a_scenario_that_is_not_public_shows_nothing(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    image_id = await upload(client, my_headers)
    scenario = await create_scenario(client, my_headers, pregens=pregens_with(image_id))
    await publish_version(client, my_headers, scenario)

    response = await client.get(image_url(scenario, image_id), headers=their_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('asset')
async def test_the_pregens_to_pick_at_a_table_carry_their_portraits(client: AsyncClient, my_headers: dict[str, str]):
    image_id = await upload(client, my_headers)
    scenario = await create_scenario(client, my_headers, pregens=pregens_with(image_id))
    number = await publish_version(client, my_headers, scenario)

    body = {'scenario_id': scenario['id'], 'version': number, 'capacity': 2}
    table = (await client.post(TABLES_URL, json=body, headers=my_headers)).json()

    assert [pregen['portrait_id'] for pregen in table['pregens']] == [image_id, None]
