# trpg-server/tests/test_portrait_tables.py

"""
테이블에서 쓰는 캐릭터 그림(#983)을 검증한다. 그림 provider, asset 서버, 결제 서버는 가짜다.

보는 것.
  - 프리젠을 고른 자리에는 그 프리젠의 그림(portrait_id)이 보인다. 직접 만든 캐릭터나 그림 없는 프리젠은 비어 있다
  - 앉은 사람 모두가 그 테이블의 판에 붙은 그림을 받는다. 앉지 않은 사람, 판에 없는 그림은 404 다
  - 장면 그림을 그릴 때 그림이 있는 캐릭터의 그림을 참고 그림으로 넘기고, 지시에 어느 그림이 누구인지 적는다
  - 참고 그림을 받지 못하면 빼고 그린다. 참고 그림을 받지 않는 provider 에는 넘기지 않는다
"""

import uuid

import pytest
from ai_core.fake import FakeImageProvider
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.main import API_PREFIX
from app.portraits.seats import pregen_portrait, table_portraits
from app.snapshots.providers import price_code_of
from tests.asset_server import FakeAsset
from tests.billing import PRICES, FakeBillingServer
from tests.narration_model import with_model
from tests.sheets import SHEET
from tests.test_round_closing import (
    FRIEND,
    ME,
    OPENINGS,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    bearer,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

STRANGER = uuid.UUID('33333333-2222-4333-8444-555555555555')
PORTRAITS_URL = f'{API_PREFIX}/portraits'
FACE = b'\x89PNG elf face'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, STRANGER)


@pytest.fixture
def asset(app: FastAPI) -> FakeAsset:
    fake = FakeAsset()
    app.state.asset = fake
    return fake


@pytest.fixture
def provider(app: FastAPI) -> FakeImageProvider:
    fake = FakeImageProvider()
    app.state.image_provider = fake
    return fake


@pytest.fixture
async def billing(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> FakeBillingServer:
    monkeypatch.setitem(PRICES, price_code_of(app.state.settings.snapshot_model), 160)
    server = FakeBillingServer(balances={ME: 1000, FRIEND: 1000})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


async def upload(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(PORTRAITS_URL, content=FACE, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


async def start_with_pregens(client: AsyncClient, me: dict[str, str], friend: dict[str, str], image_id: str) -> dict:
    """프리젠 둘(엘프는 그림이 있고 영애는 없다)의 테이블. 나는 엘프, 친구는 영애를 고르고 시작한다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    pregens = [{'name': '엘프', 'sheet': SHEET, 'image_id': image_id}, {'name': '영애', 'sheet': SHEET}]
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': OPENINGS, 'pregens': pregens}
    body['default_sheet'] = SHEET
    scenario = await client.post(SCENARIOS_URL, json=with_model(body), headers=me)
    assert scenario.status_code == status.HTTP_201_CREATED, scenario.text
    published = await client.post(f'{SCENARIOS_URL}/{scenario.json()["id"]}/versions', json={}, headers=me)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    body = {'scenario_id': scenario.json()['id'], 'version': 1, 'capacity': 2}
    table = (await client.post(TABLES_URL, json=body, headers=me)).json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await client.put(table_url(table, '/character'), json={'pregen_index': 0}, headers=me)
    await client.put(table_url(table, '/character'), json={'pregen_index': 1}, headers=friend)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


def portrait_of(table: dict, user_id: uuid.UUID) -> str | None:
    (member,) = [member for member in table['members'] if member['user_id'] == str(user_id)]
    return member['portrait_id']


def image_url(table: dict, image_id: str) -> str:
    return table_url(table, f'/portraits/{image_id}/image')


@pytest.mark.usefixtures('asset')
async def test_a_seat_with_a_pregen_shows_its_portrait(client: AsyncClient, me, friend):
    image_id = await upload(client, me)
    table = await start_with_pregens(client, me, friend, image_id)

    seen = (await client.get(table_url(table), headers=friend)).json()

    assert portrait_of(seen, ME) == image_id
    assert portrait_of(seen, FRIEND) is None


@pytest.mark.usefixtures('asset')
async def test_everyone_seated_gets_the_portraits_of_the_table(client: AsyncClient, me, friend, stranger):
    image_id = await upload(client, me)
    table = await start_with_pregens(client, me, friend, image_id)
    other = await upload(client, me)

    seated = await client.get(image_url(table, image_id), headers=friend)
    outsider = await client.get(image_url(table, image_id), headers=stranger)
    not_on_the_table = await client.get(image_url(table, other), headers=friend)

    assert (seated.status_code, seated.content) == (status.HTTP_200_OK, FACE)
    assert seated.headers['cache-control'] == 'private, max-age=3600'
    assert outsider.status_code == status.HTTP_404_NOT_FOUND
    assert (not_on_the_table.status_code, not_on_the_table.json()['code']) == (
        status.HTTP_404_NOT_FOUND,
        'portrait_not_found',
    )


@pytest.mark.usefixtures('billing')
async def test_a_drawing_passes_the_portraits_on(app: FastAPI, client: AsyncClient, me, friend, asset, provider):
    image_id = await upload(client, me)
    table = await start_with_pregens(client, me, friend, image_id)

    response = await client.post(table_url(table, '/rounds/1/snapshot'), headers=friend)
    await app.state.jobs.drain()

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    (request,) = provider.calls
    assert [reference.data for reference in request.references] == [FACE]
    assert '[참고 그림]\n1번째 그림: 엘프' in request.prompt


@pytest.mark.usefixtures('billing')
async def test_a_lost_portrait_is_left_out_of_the_drawing(
    app: FastAPI, client: AsyncClient, me, friend, asset, provider
):
    image_id = await upload(client, me)
    table = await start_with_pregens(client, me, friend, image_id)
    asset.kept.pop(uuid.UUID(image_id))

    await client.post(table_url(table, '/rounds/1/snapshot'), headers=me)
    await app.state.jobs.drain()

    (request,) = provider.calls
    assert request.references == ()
    assert '[참고 그림]' not in request.prompt
    listed = (await client.get(table_url(table, '/snapshots'), headers=me)).json()
    assert [snapshot['status'] for snapshot in listed] == ['ready']


@pytest.mark.usefixtures('billing', 'asset')
async def test_a_provider_without_references_gets_none(app: FastAPI, client: AsyncClient, me, friend):
    provider = FakeImageProvider(supports_references=False)
    app.state.image_provider = provider
    image_id = await upload(client, me)
    table = await start_with_pregens(client, me, friend, image_id)

    await client.post(table_url(table, '/rounds/1/snapshot'), headers=me)
    await app.state.jobs.drain()

    (request,) = provider.calls
    assert request.references == ()


# --- 테이블의 판에서 그림 찾기(DB 없이) ---


def test_old_tables_and_custom_characters_have_no_portrait():
    image = uuid.uuid4()
    content = {'pregens': [{'name': '엘프', 'image_id': str(image)}, {'name': '옛 판의 영애'}]}

    assert pregen_portrait(content, 0) == image
    assert pregen_portrait(content, 1) is None
    assert pregen_portrait(content, None) is None
    assert pregen_portrait(content, 5) is None
    assert pregen_portrait({}, 0) is None
    assert table_portraits(content) == {image}
