# story-server/tests/test_snapshot_charges.py

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
from server_core.testing.metrics import MetricsRecorder
from sqlalchemy import text

from app.core.dependencies import utc_now
from app.snapshots import counting
from app.snapshots.models import Snapshot, SnapshotOutcome
from app.snapshots.service import hold_reference
from app.snapshots.settler import SnapshotSettler
from app.turns.models import BillingStatus

OWNER = uuid.UUID('11111111-2222-4333-8444-555555555555')


async def stored_with(app: FastAPI, billing_status: BillingStatus, outcome: SnapshotOutcome | None) -> None:
    """
    그 청구 상태의 기록 한 장을 넣는다. 대화는 지운 것으로 둔다(대화 칸이 빈다).
    맡길 차례는 한 시간 뒤라 이 바퀴에 맡기지 않는다.
    """
    snapshot_id = uuid.uuid4()
    snapshot = Snapshot(
        id=snapshot_id,
        conversation_id=None,
        message_id=None,
        owner_id=OWNER,
        model='fake-image',
        reference=hold_reference(snapshot_id),
        price_code='story.image.fake-image',
        billing_status=billing_status,
        outcome=outcome,
        next_settle_at=utc_now() + timedelta(hours=1),
    )
    async with app.state.session_factory() as session:
        session.add(snapshot)
        await session.commit()


@pytest.mark.usefixtures('clean_tables')
async def test_the_settler_counts_unfinished_charges_by_status(app: FastAPI, metrics: MetricsRecorder):
    await stored_with(app, BillingStatus.HELD, None)
    await stored_with(app, BillingStatus.CAPTURE_DUE, SnapshotOutcome.READY)
    await stored_with(app, BillingStatus.CAPTURED, SnapshotOutcome.READY)

    await SnapshotSettler(app.state.session_factory, billing=lambda: app.state.billing).tick()

    statuses = {point.labels['status']: point.value for point in metrics.points('snapshot_charges')}
    assert statuses == {'pending': 0, 'held': 1, 'capture_due': 1, 'release_due': 0}


@pytest.mark.usefixtures('clean_tables')
async def test_an_empty_table_reports_every_status_as_zero(app: FastAPI, metrics: MetricsRecorder):
    await SnapshotSettler(app.state.session_factory, billing=lambda: app.state.billing).tick()

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

    assert 'ix_snapshots_billing_status_next_settle_at' in plan
