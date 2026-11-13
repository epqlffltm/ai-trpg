# trpg-server/tests/test_snapshot_draws.py

"""
끝난 장면 그림의 수(snapshot_draws_total, #983)를 검증한다. 그림 provider, asset, 결제 서버는 가짜다.

보는 것.
  - 다 그린 것은 outcome=ready, code=none 이다
  - 그리지 못한 것은 failed 와 그 까닭(refused, asset_unavailable)이다
  - 홀드가 걸리지 않은 것은 declined 와 그 까닭(credit_short)이다
  - 정리 작업이 그리다 만 것을 돌려주면 failed, abandoned 다
"""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from ai_core.fake import FakeImageProvider
from fastapi import FastAPI
from httpx import AsyncClient
from server_core.testing.metrics import MetricsRecorder
from server_core.testing.tokens import SigningKey

from app.billing.routing import utc_now
from app.snapshots import service
from app.snapshots.models import SnapshotBilling
from app.snapshots.providers import price_code_of
from app.snapshots.settler import SnapshotSettler
from tests.asset_server import FakeAsset
from tests.billing import PRICES, FakeBillingServer
from tests.test_round_closing import FRIEND, ME, bearer, start_duo, table_url

pytestmark = pytest.mark.usefixtures('clean_tables')

PRICE = 160
CREDITS = 1000


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


@pytest.fixture
def provider(app: FastAPI) -> FakeImageProvider:
    fake = FakeImageProvider()
    app.state.image_provider = fake
    return fake


@pytest.fixture
def asset(app: FastAPI) -> FakeAsset:
    fake = FakeAsset()
    app.state.asset = fake
    return fake


@pytest.fixture
async def billing(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeBillingServer]:
    monkeypatch.setitem(PRICES, price_code_of(app.state.settings.snapshot_model), PRICE)
    server = FakeBillingServer(balances={ME: CREDITS, FRIEND: CREDITS})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


def draws(metrics: MetricsRecorder) -> dict[tuple[str, str], float]:
    return {(point.labels['outcome'], point.labels['code']): point.value for point in metrics.points('snapshot_draws')}


async def draw_first_round(app: FastAPI, client: AsyncClient, headers: dict[str, str], table: dict) -> None:
    await client.post(table_url(table, '/rounds/1/snapshot'), headers=headers)
    await app.state.jobs.drain()


@pytest.mark.usefixtures('provider', 'asset', 'billing')
async def test_a_ready_drawing_is_counted(app: FastAPI, client: AsyncClient, me, friend, metrics: MetricsRecorder):
    table = await start_duo(client, me, friend)

    await draw_first_round(app, client, me, table)

    assert draws(metrics) == {('ready', 'none'): 1}


@pytest.mark.usefixtures('asset', 'billing')
async def test_a_refused_drawing_is_counted_with_its_reason(
    app: FastAPI, client: AsyncClient, me, friend, provider: FakeImageProvider, metrics: MetricsRecorder
):
    provider.error = 'refused'
    table = await start_duo(client, me, friend)

    await draw_first_round(app, client, me, table)

    assert draws(metrics) == {('failed', 'refused'): 1}


@pytest.mark.usefixtures('provider', 'billing')
async def test_a_dead_asset_server_is_counted(
    app: FastAPI, client: AsyncClient, me, friend, asset: FakeAsset, metrics: MetricsRecorder
):
    asset.down = True
    table = await start_duo(client, me, friend)

    await draw_first_round(app, client, me, table)

    assert draws(metrics) == {('failed', 'asset_unavailable'): 1}


@pytest.mark.usefixtures('provider', 'asset')
async def test_a_declined_hold_is_counted(
    app: FastAPI, client: AsyncClient, me, friend, billing: FakeBillingServer, metrics: MetricsRecorder
):
    billing.balances[ME] = PRICE - 1
    table = await start_duo(client, me, friend)

    await draw_first_round(app, client, me, table)

    assert draws(metrics) == {('declined', 'credit_short'): 1}


async def test_a_drawing_given_back_by_the_settler_is_counted(
    app: FastAPI, client: AsyncClient, me, friend, metrics: MetricsRecorder
):
    table = await start_duo(client, me, friend)
    snapshot = service.new_snapshot(uuid.UUID(table['id']), 1, ME, app.state.settings.snapshot_model)
    snapshot.billing_status = SnapshotBilling.HELD
    async with app.state.session_factory() as session:
        session.add(snapshot)
        await session.commit()
    later = utc_now() + service.SNAPSHOT_STALE + timedelta(minutes=1)

    await SnapshotSettler(app.state.session_factory, lambda: app.state.billing, clock=lambda: later).tick()

    assert draws(metrics) == {('failed', 'abandoned'): 1}
