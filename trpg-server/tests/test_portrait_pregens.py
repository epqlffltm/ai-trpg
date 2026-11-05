# trpg-server/tests/test_portrait_pregens.py

"""
프리젠에 붙이는 캐릭터 그림(#983)을 검증한다. asset 서버는 가짜다(tests/asset_server.py).

보는 것.
  - 자기가 올린 그림을 프리젠에 붙여 저장하고 읽는다. 게시한 판에도 그대로 실린다
  - 남의 그림, 없는 그림, 이 서버에 올리지 않은 그림은 붙이지 못한다(422). 아무것도 저장하지 않는다
  - 고칠 때도 같다. 프리젠을 보내지 않으면 붙인 그림은 그대로다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.main import API_PREFIX
from tests.asset_server import FakeAsset
from tests.narration_model import asset_body
from tests.sheets import as_character
from tests.test_versions_api import SCENARIOS_URL, SHEET, create_ready_scenario, publish
from tests.test_versions_api import my_headers as my_headers  # noqa: F401  (픽스처)
from tests.test_versions_api import their_headers as their_headers  # noqa: F401  (픽스처)

pytestmark = pytest.mark.usefixtures('clean_tables')

PORTRAITS_URL = f'{API_PREFIX}/portraits'


@pytest.fixture
def asset(app: FastAPI) -> FakeAsset:
    """앱에 꽂은 가짜 asset 서버."""
    fake = FakeAsset()
    app.state.asset = fake
    return fake


async def upload(client: AsyncClient, headers: dict[str, str]) -> str:
    """그림 하나를 올리고 그 id 를 돌려준다."""
    response = await client.post(PORTRAITS_URL, content=b'\x89PNG face', headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


def pregen(image_id: str | None) -> dict:
    return {'name': '폭주족 엘프', 'sheet': SHEET, 'image_id': image_id}


@pytest.mark.usefixtures('asset')
async def test_my_portrait_is_kept_on_the_pregen_and_in_the_version(client: AsyncClient, my_headers: dict[str, str]):
    image_id = await upload(client, my_headers)

    scenario = await create_ready_scenario(client, my_headers, pregens=[pregen(image_id)])
    version = await publish(client, my_headers, scenario)

    assert scenario['pregens'][0]['image_id'] == image_id
    assert version['snapshot']['pregens'][0]['image_id'] == image_id
    assert version['snapshot']['pregens'][0]['sheet'] == as_character(SHEET)


@pytest.mark.usefixtures('asset')
async def test_someone_elses_or_an_unknown_portrait_is_refused(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await upload(client, their_headers)

    for image_id in (theirs, str(uuid.uuid4())):
        body = asset_body(SCENARIOS_URL, {'title': '추격전', 'pregens': [pregen(image_id)]})
        response = await client.post(SCENARIOS_URL, json=body, headers=my_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
        assert 'pregens.image_id' in response.json()['detail']

    listed = await client.get(SCENARIOS_URL, headers=my_headers)
    assert listed.json()['total'] == 0


@pytest.mark.usefixtures('asset')
async def test_an_update_checks_the_portrait_and_keeps_it_when_pregens_are_not_sent(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    mine = await upload(client, my_headers)
    theirs = await upload(client, their_headers)
    scenario = await create_ready_scenario(client, my_headers, pregens=[pregen(mine)])
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    refused = await client.patch(url, json={'pregens': [pregen(theirs)]}, headers=my_headers)
    untouched = await client.patch(url, json={'description': '메모'}, headers=my_headers)
    cleared = await client.patch(url, json={'pregens': [pregen(None)]}, headers=my_headers)

    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert untouched.json()['pregens'][0]['image_id'] == mine
    assert cleared.json()['pregens'][0]['image_id'] is None
