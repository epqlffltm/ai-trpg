# trpg-server/tests/test_snapshots_api.py

"""
테이블의 장면 그림(#983)의 API 를 검증한다. 그림 provider 는 가짜(ai_core 의 FakeImageProvider), asset 서버도 가짜다
(tests/asset_server.py). 결제 서버는 가짜 결제 서버를 꽂는다(tests/billing.py).

보는 것.
  - 앉은 사람 누구나 그 라운드의 장면을 그린다. 202 로 그리는 중을 돌려주고, 다 그리면 누른 사람의 값을 확정한다
  - 그림은 누른 사람의 토큰으로 asset 에 맡긴다. 앉은 사람 모두가 목록에서 보고 이 서버를 거쳐 바이트를 받는다
  - 지시에는 그 라운드의 장면과 테이블의 제목, 캐릭터의 이름이 들어간다
  - 앉지 않은 사람에게는 테이블이 없다(404). 없는 라운드도 404 다
  - 크레딧이 모자라면 402 이고 실패로 남는다. 실패의 까닭은 누른 사람에게만 보인다
  - 그리지 못하면(공급자의 거절, asset 이 죽었다) 실패로 적고 돌려준다
  - 한 테이블에 그리는 중인 것은 하나다(409)
  - provider 가 없으면 503 snapshot_unavailable 이고, 값은 available=false 다
  - 정리 작업은 그리는 도중에 오래 남은 것을 실패로 적고 돌려준다
  - 그리기 시작과 끝은 앉은 사람 모두의 스트림에 scene_snapshot 으로 알린다(그린 사람에게도).
    다른 테이블에는 가지 않는다
"""

import asyncio
import uuid
from datetime import timedelta

import pytest
from ai_core.fake import FAKE_PNG, FakeImageProvider
from ai_core.image_provider import GeneratedImage, ImageRequest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.billing.routing import utc_now
from app.main import API_PREFIX
from app.realtime.service import SNAPSHOT_FRAME, Cursor
from app.realtime.sse import Frame
from app.snapshots import service
from app.snapshots.models import SnapshotBilling, SnapshotOutcome, TableSnapshot
from app.snapshots.providers import price_code_of
from app.snapshots.settler import SnapshotSettler
from tests.asset_server import FakeAsset
from tests.billing import PRICES, FakeBillingServer
from tests.streaming import Reader
from tests.test_round_closing import FRIEND, ME, OPENINGS, bearer, start_duo, table_url

pytestmark = pytest.mark.usefixtures('clean_tables')

STRANGER = uuid.UUID('33333333-2222-4333-8444-555555555555')
# 다른 테이블에 함께 앉는 사람
OUTSIDER = uuid.UUID('44444444-2222-4333-8444-555555555555')
# 장면 그림 한 장의 값(가짜 결제 서버의 가격표)
PRICE = 160
CREDITS = 1000


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
def outsider(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, OUTSIDER)


@pytest.fixture
def provider(app: FastAPI) -> FakeImageProvider:
    """앱에 꽂은 가짜 그림 provider."""
    fake = FakeImageProvider()
    app.state.image_provider = fake
    return fake


@pytest.fixture
def asset(app: FastAPI) -> FakeAsset:
    """앱에 꽂은 가짜 asset 서버."""
    fake = FakeAsset()
    app.state.asset = fake
    return fake


@pytest.fixture
async def billing(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 장면 그림의 가격표가 있고, 둘 다 크레딧이 넉넉하다."""
    monkeypatch.setitem(PRICES, price_code_of(app.state.settings.snapshot_model), PRICE)
    server = FakeBillingServer(balances={ME: CREDITS, FRIEND: CREDITS})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


def snapshot_url(table: dict, number: int = 1) -> str:
    return table_url(table, f'/rounds/{number}/snapshot')


async def draw(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """그 테이블의 첫 라운드를 그리기 시작한다."""
    response = await client.post(snapshot_url(table), headers=headers)
    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    return response.json()


async def listed(client: AsyncClient, headers: dict[str, str], table: dict) -> list[dict]:
    response = await client.get(table_url(table, '/snapshots'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def drawn(app: FastAPI) -> None:
    """맡긴 작업이 끝나기를 기다린다."""
    await app.state.jobs.drain()


def holds_of(billing: FakeBillingServer, user_id: uuid.UUID) -> list[str]:
    """그 사람의 장면 그림 홀드의 상태들."""
    return [
        hold.status
        for name, hold in billing.holds.items()
        if name.startswith('game:img:') and hold.user_id == str(user_id)
    ]


@pytest.mark.usefixtures('asset')
async def test_anyone_seated_draws_and_pays_and_everyone_sees_it(
    app: FastAPI, client: AsyncClient, me, friend, provider, billing
):
    table = await start_duo(client, me, friend)

    started = await draw(client, friend, table)
    await drawn(app)

    assert (started['status'], started['round_number'], started['by_me']) == ('drawing', 1, True)
    (seen,) = await listed(client, me, table)
    assert (seen['id'], seen['status'], seen['by_me'], seen['code']) == (started['id'], 'ready', False, None)
    assert holds_of(billing, FRIEND) == ['captured']
    assert (billing.balance(FRIEND), billing.balance(ME)) == (CREDITS - PRICE, CREDITS)


async def test_the_image_is_kept_for_the_drawer_and_passed_on_to_the_table(
    app: FastAPI, client: AsyncClient, me, friend, provider, asset, billing
):
    table = await start_duo(client, me, friend)
    started = await draw(client, friend, table)
    await drawn(app)

    response = await client.get(table_url(table, f'/snapshots/{started["id"]}/image'), headers=me)

    assert response.status_code == status.HTTP_200_OK
    assert (response.content, response.headers['content-type']) == (FAKE_PNG, 'image/png')
    assert response.headers['cache-control'].startswith('private')
    (owner,) = asset.owners.values()
    assert owner == friend['Authorization'].removeprefix('Bearer ')


@pytest.mark.usefixtures('asset', 'billing')
async def test_the_prompt_is_the_scene_of_the_round(app: FastAPI, client: AsyncClient, me, friend, provider):
    table = await start_duo(client, me, friend)

    await draw(client, me, table)
    await drawn(app)

    (request,) = provider.calls
    assert OPENINGS[0] in request.prompt
    assert '추격전' in request.prompt
    assert '엘프' in request.prompt and '영애' in request.prompt
    assert '전체이용가' in request.prompt


@pytest.mark.usefixtures('provider', 'asset', 'billing')
async def test_a_stranger_finds_no_table(app: FastAPI, client: AsyncClient, me, friend, stranger):
    table = await start_duo(client, me, friend)
    started = await draw(client, me, table)
    await drawn(app)

    tried = await client.post(snapshot_url(table), headers=stranger)
    looked = await client.get(table_url(table, '/snapshots'), headers=stranger)
    fetched = await client.get(table_url(table, f'/snapshots/{started["id"]}/image'), headers=stranger)

    assert [tried.status_code, looked.status_code, fetched.status_code] == [status.HTTP_404_NOT_FOUND] * 3


@pytest.mark.usefixtures('provider', 'asset', 'billing')
async def test_a_missing_round_is_not_found(client: AsyncClient, me, friend):
    table = await start_duo(client, me, friend)

    response = await client.post(snapshot_url(table, 99), headers=me)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('provider', 'asset')
async def test_short_credits_are_402_and_the_reason_is_only_the_drawers(
    client: AsyncClient, me, friend, billing: FakeBillingServer
):
    billing.balances[FRIEND] = PRICE - 1
    table = await start_duo(client, me, friend)

    response = await client.post(snapshot_url(table), headers=friend)

    assert (response.status_code, response.json()['code']) == (status.HTTP_402_PAYMENT_REQUIRED, 'credit_short')
    assert [(s['status'], s['code']) for s in await listed(client, friend, table)] == [('failed', 'credit_short')]
    assert [(s['status'], s['code']) for s in await listed(client, me, table)] == [('failed', None)]


@pytest.mark.usefixtures('asset')
async def test_a_refused_drawing_is_given_back(
    app: FastAPI, client: AsyncClient, me, friend, provider, billing: FakeBillingServer
):
    provider.error = 'refused'
    table = await start_duo(client, me, friend)

    await draw(client, me, table)
    await drawn(app)

    assert [(s['status'], s['code']) for s in await listed(client, me, table)] == [('failed', 'refused')]
    assert holds_of(billing, ME) == ['released']
    assert billing.balance(ME) == CREDITS


@pytest.mark.usefixtures('provider')
async def test_a_dead_asset_server_is_given_back(
    app: FastAPI, client: AsyncClient, me, friend, asset: FakeAsset, billing: FakeBillingServer
):
    asset.down = True
    table = await start_duo(client, me, friend)

    started = await draw(client, me, table)
    await drawn(app)
    fetched = await client.get(table_url(table, f'/snapshots/{started["id"]}/image'), headers=me)

    assert [(s['status'], s['code']) for s in await listed(client, me, table)] == [('failed', 'asset_unavailable')]
    assert holds_of(billing, ME) == ['released']
    assert fetched.json()['code'] == 'snapshot_not_found'


@pytest.mark.usefixtures('provider', 'billing')
async def test_a_kept_image_behind_a_dead_asset_server_is_503(
    app: FastAPI, client: AsyncClient, me, friend, asset: FakeAsset
):
    table = await start_duo(client, me, friend)
    started = await draw(client, me, table)
    await drawn(app)
    asset.down = True

    response = await client.get(table_url(table, f'/snapshots/{started["id"]}/image'), headers=friend)

    assert (response.status_code, response.json()['code']) == (status.HTTP_503_SERVICE_UNAVAILABLE, 'asset_unavailable')


class GatedProvider:
    """문이 열릴 때까지 그리지 않는 provider."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        await self.gate.wait()
        return GeneratedImage(data=FAKE_PNG, mime_type='image/png', model='fake')


@pytest.mark.usefixtures('asset', 'billing')
async def test_one_drawing_at_a_time_per_table(app: FastAPI, client: AsyncClient, me, friend):
    gated = GatedProvider()
    app.state.image_provider = gated
    table = await start_duo(client, me, friend)
    started = await draw(client, me, table)

    second = await client.post(snapshot_url(table), headers=friend)
    gated.gate.set()
    await drawn(app)

    assert (second.status_code, second.json()['code']) == (status.HTTP_409_CONFLICT, 'snapshot_in_progress')
    assert [s['id'] for s in await listed(client, friend, table)] == [started['id']]


async def test_a_server_that_does_not_draw_says_so(app: FastAPI, client: AsyncClient, me, friend):
    app.state.image_provider = None
    table = await start_duo(client, me, friend)

    tried = await client.post(snapshot_url(table), headers=me)
    price = await client.get(f'{API_PREFIX}/snapshots/price', headers=me)

    assert (tried.status_code, tried.json()['code']) == (status.HTTP_503_SERVICE_UNAVAILABLE, 'snapshot_unavailable')
    assert price.json() == {'available': False, 'credits': None, 'tier': None, 'promo': False}
    assert await listed(client, me, table) == []


@pytest.mark.usefixtures('provider')
async def test_without_a_billing_server_the_price_is_open(client: AsyncClient, me):
    response = await client.get(f'{API_PREFIX}/snapshots/price', headers=me)

    assert response.json() == {'available': True, 'credits': None, 'tier': None, 'promo': False}


@pytest.mark.usefixtures('asset')
async def test_a_drawing_stopped_by_shutdown_is_given_back_by_the_settler(
    app: FastAPI, client: AsyncClient, me, friend, billing: FakeBillingServer
):
    app.state.image_provider = GatedProvider()
    table = await start_duo(client, me, friend)
    await draw(client, me, table)

    await app.state.jobs.aclose(grace=0.01)
    settler = SnapshotSettler(app.state.session_factory, lambda: app.state.billing)
    assert holds_of(billing, ME) == ['held']
    assert await settler.tick() == 1

    assert [(s['status'], s['code']) for s in await listed(client, me, table)] == [('failed', 'cancelled')]
    assert holds_of(billing, ME) == ['released']


async def test_the_settler_gives_back_a_drawing_left_behind(
    app: FastAPI, client: AsyncClient, me, friend, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)
    snapshot = service.new_snapshot(uuid.UUID(table['id']), 1, ME, app.state.settings.snapshot_model)
    snapshot.billing_status = SnapshotBilling.HELD
    async with app.state.session_factory() as session:
        session.add(snapshot)
        await session.commit()
    await app.state.billing.hold(snapshot.reference, ME, snapshot.price_code)
    later = utc_now() + service.SNAPSHOT_STALE + timedelta(minutes=1)
    settler = SnapshotSettler(app.state.session_factory, lambda: app.state.billing, clock=lambda: later)

    assert await settler.tick() == 1

    assert [(s['status'], s['code']) for s in await listed(client, me, table)] == [('failed', 'abandoned')]
    assert holds_of(billing, ME) == ['released']
    async with app.state.session_factory() as session:
        stored = await session.get(TableSnapshot, snapshot.id)
    assert (stored.billing_status, stored.outcome) == (SnapshotBilling.RELEASED, SnapshotOutcome.FAILED)


async def test_the_settler_leaves_a_fresh_drawing_alone(app: FastAPI, client: AsyncClient, me, friend):
    table = await start_duo(client, me, friend)
    snapshot = service.new_snapshot(uuid.UUID(table['id']), 1, ME, app.state.settings.snapshot_model)
    async with app.state.session_factory() as session:
        session.add(snapshot)
        await session.commit()
    settler = SnapshotSettler(app.state.session_factory, lambda: app.state.billing)

    assert await settler.tick() == 0
    assert [s['status'] for s in await listed(client, me, table)] == ['drawing']


async def snapshot_frames_of(reader: Reader, limit: int = 20) -> list[Frame]:
    """스트림에서 장면 그림의 알림만 고른다. 조용해질 때까지 읽는다."""
    found = []
    for _ in range(limit):
        try:
            frame = await reader.next(timeout=0.5)
        except TimeoutError:
            break
        if frame.event == SNAPSHOT_FRAME:
            found.append(frame)
    return found


@pytest.mark.usefixtures('provider', 'asset', 'billing')
async def test_drawing_is_announced_to_everyone_at_the_table(app: FastAPI, client: AsyncClient, me, friend, connect):
    table = await start_duo(client, me, friend)
    mine, friends = connect(table, ME, Cursor(events=1000)), connect(table, FRIEND, Cursor(events=1000))
    await mine.settle()
    await friends.settle()

    await draw(client, friend, table)
    await drawn(app)

    for reader in (mine, friends):
        frames = await snapshot_frames_of(reader)
        assert frames, '장면 그림의 알림이 오지 않았다'
        assert {(frame.data, frame.id) for frame in frames} == {('{}', None)}


@pytest.mark.usefixtures('provider', 'asset', 'billing')
async def test_drawing_is_not_announced_to_another_table(
    app: FastAPI, client: AsyncClient, me, friend, stranger, outsider, connect
):
    table = await start_duo(client, me, friend)
    other = await start_duo(client, stranger, outsider)
    strangers = connect(other, STRANGER, Cursor(events=1000))
    await strangers.settle()

    await draw(client, me, table)
    await drawn(app)

    assert await snapshot_frames_of(strangers) == []


async def test_the_settler_announces_a_drawing_it_gives_back(app: FastAPI, client: AsyncClient, me, friend, connect):
    table = await start_duo(client, me, friend)
    snapshot = service.new_snapshot(uuid.UUID(table['id']), 1, ME, app.state.settings.snapshot_model)
    snapshot.billing_status = SnapshotBilling.HELD
    async with app.state.session_factory() as session:
        session.add(snapshot)
        await session.commit()
    friends = connect(table, FRIEND, Cursor(events=1000))
    await friends.settle()
    later = utc_now() + service.SNAPSHOT_STALE + timedelta(minutes=1)
    settler = SnapshotSettler(app.state.session_factory, lambda: app.state.billing, clock=lambda: later)

    await settler.tick()

    assert len(await snapshot_frames_of(friends)) == 1
