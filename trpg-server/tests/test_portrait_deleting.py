# trpg-server/tests/test_portrait_deleting.py

"""
캐릭터 그림(#983)을 지우는 것을 검증한다. asset 서버는 가짜다(tests/asset_server.py).

보는 것.
  - 어느 초안이나 판에도 붙지 않은 그림은 지운다(204). 기록과 asset 의 그림이 함께 사라지고, 다시 붙이지 못한다
  - 초안의 프리젠에 붙어 있거나, 초안에서 뗐어도 게시한 판에 남아 있으면 409 이고 쓰는 시나리오를 알린다
  - 지운 초안에만 붙어 있던 그림은 지운다. 지운 시나리오라도 판에 쓰였으면 409 다
  - 남의 그림은 404 다
  - asset 이 죽었어도 기록은 지운다(asset 에 그림이 남는다)
  - 그림을 붙이는 저장이 진행 중이면 지우기는 그 저장이 끝날 때까지 기다리고, 붙었으면 409 다
"""

import asyncio
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import update

from app.assets.models import Scenario
from app.main import API_PREFIX
from app.portraits import repository
from tests.asset_server import FakeAsset
from tests.narration_model import asset_body
from tests.sheets import SHEET
from tests.test_versions_api import ME, SCENARIOS_URL, create_ready_scenario, publish
from tests.test_versions_api import my_headers as my_headers  # noqa: F401  (픽스처)
from tests.test_versions_api import their_headers as their_headers  # noqa: F401  (픽스처)

pytestmark = pytest.mark.usefixtures('clean_tables')

PORTRAITS_URL = f'{API_PREFIX}/portraits'


@pytest.fixture
def asset(app) -> FakeAsset:
    fake = FakeAsset()
    app.state.asset = fake
    return fake


async def upload(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(PORTRAITS_URL, content=b'\x89PNG face', headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


def pregen(image_id: str | None) -> dict:
    return {'name': '엘프', 'sheet': SHEET, 'image_id': image_id}


async def delete(client: AsyncClient, headers: dict[str, str], image_id: str):
    return await client.delete(f'{PORTRAITS_URL}/{image_id}', headers=headers)


async def test_an_unused_portrait_is_deleted_with_its_image(client: AsyncClient, my_headers: dict[str, str], asset):
    image_id = await upload(client, my_headers)

    deleted = await delete(client, my_headers, image_id)
    listed = (await client.get(PORTRAITS_URL, headers=my_headers)).json()
    image = await client.get(f'{PORTRAITS_URL}/{image_id}/image', headers=my_headers)
    body = asset_body(SCENARIOS_URL, {'title': '추격전', 'pregens': [pregen(image_id)]})
    attached = await client.post(SCENARIOS_URL, json=body, headers=my_headers)

    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert listed['total'] == 0
    assert [str(discarded) for discarded in asset.discarded] == [image_id]
    assert image.status_code == status.HTTP_404_NOT_FOUND
    assert attached.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.usefixtures('asset')
async def test_a_portrait_on_a_draft_is_kept_and_the_scenario_is_named(client: AsyncClient, my_headers: dict[str, str]):
    image_id = await upload(client, my_headers)
    scenario = await create_ready_scenario(client, my_headers, title='추격전', pregens=[pregen(image_id)])

    response = await delete(client, my_headers, image_id)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['code'] == 'portrait_in_use'
    assert response.json()['scenarios'] == [{'id': scenario['id'], 'title': '추격전'}]
    assert (await client.get(PORTRAITS_URL, headers=my_headers)).json()['total'] == 1


@pytest.mark.usefixtures('asset')
async def test_a_portrait_left_in_a_published_version_is_kept(client: AsyncClient, my_headers: dict[str, str]):
    image_id = await upload(client, my_headers)
    scenario = await create_ready_scenario(client, my_headers, pregens=[pregen(image_id)])
    await publish(client, my_headers, scenario)
    url = f'{SCENARIOS_URL}/{scenario["id"]}'
    await client.patch(url, json={'pregens': [pregen(None)]}, headers=my_headers)
    in_version = await delete(client, my_headers, image_id)

    await client.delete(url, headers=my_headers)
    after_deleting_the_scenario = await delete(client, my_headers, image_id)

    assert in_version.status_code == status.HTTP_409_CONFLICT
    assert after_deleting_the_scenario.status_code == status.HTTP_409_CONFLICT


@pytest.mark.usefixtures('asset')
async def test_a_portrait_only_on_a_deleted_draft_is_deleted(client: AsyncClient, my_headers: dict[str, str]):
    image_id = await upload(client, my_headers)
    scenario = await create_ready_scenario(client, my_headers, pregens=[pregen(image_id)])
    await client.delete(f'{SCENARIOS_URL}/{scenario["id"]}', headers=my_headers)

    response = await delete(client, my_headers, image_id)

    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.usefixtures('asset')
async def test_someone_elses_portrait_is_not_found(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    image_id = await upload(client, their_headers)

    response = await delete(client, my_headers, image_id)

    assert (response.status_code, response.json()['code']) == (status.HTTP_404_NOT_FOUND, 'portrait_not_found')


async def test_a_dead_asset_server_still_forgets_the_portrait(client: AsyncClient, my_headers: dict[str, str], asset):
    image_id = await upload(client, my_headers)
    asset.down = True

    response = await delete(client, my_headers, image_id)

    asset.down = False
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert (await client.get(PORTRAITS_URL, headers=my_headers)).json()['total'] == 0


# --- 붙이는 저장과 지우기가 겹칠 때 ---


@pytest.mark.usefixtures('asset')
async def test_deleting_waits_for_a_save_that_attaches_the_portrait(
    app, client: AsyncClient, my_headers: dict[str, str]
):
    image_id = await upload(client, my_headers)
    scenario = await create_ready_scenario(client, my_headers, pregens=[pregen(None)])

    async with app.state.session_factory() as saving:
        # 시나리오 저장이 그림을 확인했다(나눠 잠금). 아직 저장하지 않았다
        assert await repository.owned_ids(saving, ME, {uuid.UUID(image_id)}) == {uuid.UUID(image_id)}
        deleting = asyncio.create_task(delete(client, my_headers, image_id))
        await asyncio.sleep(0.3)
        waited = not deleting.done()
        await saving.execute(
            update(Scenario)
            .where(Scenario.asset_id == uuid.UUID(scenario['id']))
            .values(pregens=[{**pregen(image_id), 'sheet': None}])
        )
        await saving.commit()

    response = await deleting

    assert waited
    assert response.status_code == status.HTTP_409_CONFLICT
