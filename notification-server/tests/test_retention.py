# notification-server/tests/test_retention.py

"""
보관 기간이 지난 알림을 지우는 정리 작업(app/notifications/retention.py)을 검증한다.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications import retention
from app.notifications.models import Notification
from app.notifications.retention import NotificationPruner

pytestmark = pytest.mark.usefixtures('clean_tables')

NOW = datetime(2026, 11, 30, 12, 0, tzinfo=UTC)
USER = uuid.UUID('0b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
LOGGER = 'app.notifications.retention'


def make_pruner(app: FastAPI, **overrides) -> NotificationPruner:
    values = {'session_factory': app.state.session_factory, 'retention_days': 30, 'clock': lambda: NOW}
    values.update(overrides)
    return NotificationPruner(**values)


async def add_received_at(session: AsyncSession, *moments: datetime, read: bool = False) -> None:
    """그 시각들에 받은 알림을 넣는다."""
    session.add_all(
        Notification(
            user_id=USER,
            source='game',
            source_key=str(uuid.uuid4()),
            kind='scenario.sanctioned',
            payload={},
            created_at=moment,
            read_at=moment if read else None,
        )
        for moment in moments
    )
    await session.commit()


async def remaining(session: AsyncSession) -> list[datetime]:
    session.expire_all()
    return list(await session.scalars(select(Notification.created_at).order_by(Notification.created_at)))


async def test_deletes_only_what_is_past_the_retention(app: FastAPI, session: AsyncSession):
    edge = NOW - timedelta(days=30)
    await add_received_at(session, edge - timedelta(seconds=1), edge, NOW - timedelta(days=1))

    deleted = await make_pruner(app).tick()

    assert deleted == 1
    # 꼭 30일 된 것은 남는다. 30일을 넘긴 것만 지운다
    assert await remaining(session) == [edge, NOW - timedelta(days=1)]


async def test_unread_notifications_are_deleted_too(app: FastAPI, session: AsyncSession):
    # 보관 기간은 받은 시각부터 센다. 읽지 않았다고 끝없이 두지 않는다
    await add_received_at(session, NOW - timedelta(days=40))
    await add_received_at(session, NOW - timedelta(days=40), read=True)

    assert await make_pruner(app).tick() == 2


async def test_deletes_in_batches_and_leaves_the_rest_for_the_next_round(
    monkeypatch: pytest.MonkeyPatch, app: FastAPI, session: AsyncSession
):
    monkeypatch.setattr(retention, 'PRUNE_BATCH', 2)
    monkeypatch.setattr(retention, 'PRUNE_MAX_BATCHES', 2)
    old = NOW - timedelta(days=60)
    await add_received_at(session, *(old + timedelta(minutes=index) for index in range(5)))

    first = await make_pruner(app).tick()
    second = await make_pruner(app).tick()

    # 한 바퀴에 2개씩 2묶음까지다. 오래된 것부터 지운다
    assert (first, second) == (4, 1)
    assert await remaining(session) == []


async def test_a_round_is_logged_with_its_own_job_id(
    app: FastAPI, session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    await add_received_at(session, NOW - timedelta(days=40))

    with caplog.at_level(logging.INFO, logger=LOGGER):
        await make_pruner(app).tick()

    (record,) = [entry for entry in caplog.records if entry.name == LOGGER]
    assert (record.operation, record.deleted, record.retention_days) == ('notification.prune', 1, 30)
    assert record.levelno == logging.INFO


async def test_a_round_that_deletes_nothing_is_only_debug(app: FastAPI, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        await make_pruner(app).tick()

    assert [entry for entry in caplog.records if entry.name == LOGGER] == []


async def test_a_failed_round_is_logged_and_the_loop_goes_on(
    monkeypatch: pytest.MonkeyPatch, app: FastAPI, caplog: pytest.LogCaptureFixture
):
    rounds = 0

    async def broken_sweep(self) -> int:
        nonlocal rounds
        rounds += 1
        raise RuntimeError('DB 가 없다')

    monkeypatch.setattr(NotificationPruner, 'sweep', broken_sweep)
    pruner = make_pruner(app, interval=0.01)

    with caplog.at_level(logging.ERROR, logger=LOGGER):
        running = retention.start(pruner)
        while rounds < 2:
            await asyncio.sleep(0.01)
        await asyncio.wait_for(running.halt(), timeout=1)

    # 한 바퀴가 통째로 실패해도 멈추지 않는다. 바퀴마다 error 한 줄이다
    failures = [entry for entry in caplog.records if entry.name == LOGGER]
    assert len(failures) >= 2
    assert {entry.error_code for entry in failures} == {'job.failed'}


async def test_the_app_keeps_thirty_days_by_default(app: FastAPI):
    assert app.state.notification_pruner.retention_days == 30


async def test_the_default_clock_is_now(app: FastAPI, session: AsyncSession):
    await add_received_at(session, datetime.now(UTC) - timedelta(days=31), datetime.now(UTC))
    pruner = NotificationPruner(session_factory=app.state.session_factory, retention_days=30)

    assert await pruner.tick() == 1
    assert (await session.scalar(select(func.count()).select_from(Notification))) == 1
