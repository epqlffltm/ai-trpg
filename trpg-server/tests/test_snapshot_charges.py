# trpg-server/tests/test_snapshot_charges.py

"""
끝나지 않은 장면 그림의 청구의 수(snapshot_charges, #983)를 검증한다.

보는 것.
  - 정리 작업은 바퀴마다 끝나지 않은 청구의 수를 상태마다 센다. 없는 상태도 0 이고, 끝난 것은 세지 않는다
  - 그 셈은 청구 상태의 색인을 탄다(끝난 청구가 쌓여도 표 전체를 읽지 않는다)
"""

import uuid
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from server_core.testing.metrics import MetricsRecorder
from server_core.testing.tokens import SigningKey
from sqlalchemy import text

from app.billing.routing import utc_now
from app.snapshots import counting, service
from app.snapshots.models import SnapshotBilling, SnapshotOutcome
from app.snapshots.settler import SnapshotSettler
from tests.test_round_closing import FRIEND, ME, bearer, start_duo


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


async def stored_with(app: FastAPI, table: dict, billing_status: SnapshotBilling, outcome: SnapshotOutcome | None):
    """그 청구 상태의 기록 한 장을 넣는다. 맡길 차례는 한 시간 뒤라 이 바퀴에 맡기지 않는다."""
    snapshot = service.new_snapshot(uuid.UUID(table['id']), 1, ME, app.state.settings.snapshot_model)
    snapshot.billing_status = billing_status
    snapshot.outcome = outcome
    snapshot.next_settle_at = utc_now() + timedelta(hours=1)
    async with app.state.session_factory() as session:
        session.add(snapshot)
        await session.commit()


@pytest.mark.usefixtures('clean_tables')
async def test_the_settler_counts_unfinished_charges_by_status(
    app: FastAPI, client: AsyncClient, me, friend, metrics: MetricsRecorder
):
    # 한 테이블에 그리는 중인 것은 하나다. 둘째 테이블에 끝난 것들을 둔다
    first = await start_duo(client, me, friend)
    second = await start_duo(client, me, friend)
    await stored_with(app, first, SnapshotBilling.HELD, None)
    await stored_with(app, second, SnapshotBilling.CAPTURE_DUE, SnapshotOutcome.READY)
    await stored_with(app, second, SnapshotBilling.CAPTURED, SnapshotOutcome.READY)

    await SnapshotSettler(app.state.session_factory, lambda: app.state.billing).tick()

    statuses = {point.labels['status']: point.value for point in metrics.points('snapshot_charges')}
    assert statuses == {'pending': 0, 'held': 1, 'capture_due': 1, 'release_due': 0}


@pytest.mark.usefixtures('clean_tables')
async def test_an_empty_table_reports_every_status_as_zero(app: FastAPI, metrics: MetricsRecorder):
    await SnapshotSettler(app.state.session_factory, lambda: app.state.billing).tick()

    statuses = {point.labels['status']: point.value for point in metrics.points('snapshot_charges')}
    assert statuses == {status.value: 0 for status in counting.UNFINISHED_STATUSES}


async def test_counting_unfinished_charges_reads_the_status_index(app: FastAPI):
    # 표가 작으면 PostgreSQL 이 표를 읽는 쪽을 고르므로 그 길을 막고 계획을 본다
    query = counting.unfinished_by_status().compile(
        app.state.engine.sync_engine, compile_kwargs={'literal_binds': True}
    )
    async with app.state.engine.connect() as connection:
        await connection.execute(text('SET LOCAL enable_seqscan = off'))
        plan = '\n'.join(row[0] for row in await connection.execute(text(f'EXPLAIN {query}')))

    assert 'ix_table_snapshots_billing_status_next_settle_at' in plan
