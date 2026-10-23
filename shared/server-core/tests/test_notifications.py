# shared/server-core/tests/test_notifications.py

"""
발송함(server_core/notifications/)을 DB 없이 검증한다. 실제 쿼리(repository.py, store.py)는 쓰는 서버의 테스트가 본다.

  - 칸: 서버의 Base 와 물려받으면 이름 붙은 제약과 기다리는 것만 담는 색인이 생긴다
  - 알림 서버를 부르는 것: 주소의 서버 이름, 본문, 서명, 답의 뜻(보냈다, 다시 보낼 일, 받지 않았다)
  - 보내는 작업: 보내면 지우고, 못 보내면 기다리는 시간을 늘려 다시 보내고, 받지 않으면 실패로 둔다.
    오래 못 보낸 것은 지운다. 주소가 없으면 보내지 않는다. 한 알림이 예외로 끝나도 다른 알림은 보낸다.
  - 설정: 환경 변수로 읽고, 주소를 적으면 비밀이 32자 이상이어야 한다
"""

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import MetaData
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import CreateIndex, CreateTable

from server_core.database import NAMING_CONVENTION
from server_core.notifications import dispatcher as dispatching
from server_core.notifications.client import Delivery, HttpNotifications, Sent, encode, put_path
from server_core.notifications.dispatcher import (
    DISPATCH_OPERATION,
    REJECTED_ERROR_CODE,
    STALE_AFTER,
    UNAVAILABLE_ERROR_CODE,
    NotificationDispatcher,
    retry_delay,
)
from server_core.notifications.models import OutboxStatus, OutgoingNotificationColumns
from server_core.notifications.settings import NotificationSettings
from server_core.notifications.setup import build_notifications
from tests.conftest import TEST_JWKS_URL, TestSettings

USER = uuid.UUID('11111111-2222-4333-8444-555555555555')
NOW = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)
SECRET = 'n' * 40
BASE_URL = 'http://notification.test'


class Base(DeclarativeBase):
    """서버의 Base 와 같은 모양."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class OutgoingNotification(OutgoingNotificationColumns, Base):
    """서버가 만드는 발송함 표와 같은 모양."""


def row(key: str, notification_id: int = 1, **values) -> OutgoingNotification:
    """발송함의 한 줄. DB 에 넣지 않는다. 적을 때의 기본값을 채운다."""
    defaults = {'status': OutboxStatus.PENDING, 'attempts': 0, 'next_attempt_at': None, 'created_at': NOW}
    return OutgoingNotification(
        id=notification_id,
        source_key=key,
        user_id=USER,
        kind='character.hidden',
        payload={'character_id': 'c1', 'name': '렌'},
        **{**defaults, **values},
    )


@dataclass
class FakeStore:
    """메모리의 발송함. repository.py 와 같은 규칙이다(바꾸는 것은 기다리는 줄만)."""

    rows: list[OutgoingNotification] = field(default_factory=list)
    limits: list[int] = field(default_factory=list)

    def find(self, notification_id: int) -> OutgoingNotification | None:
        return next((item for item in self.rows if item.id == notification_id), None)

    def pending(self, notification_id: int) -> OutgoingNotification | None:
        found = self.find(notification_id)
        return found if found is not None and found.status == OutboxStatus.PENDING else None

    async def drop_stale(self, cutoff: datetime) -> int:
        stale = [item for item in self.rows if item.status == OutboxStatus.PENDING and item.created_at < cutoff]
        self.rows = [item for item in self.rows if item not in stale]
        return len(stale)

    async def due(self, now: datetime, limit: int) -> list[OutgoingNotification]:
        self.limits.append(limit)
        ready = [
            item
            for item in self.rows
            if item.status == OutboxStatus.PENDING and (item.next_attempt_at is None or item.next_attempt_at <= now)
        ]
        return sorted(ready, key=lambda item: item.id)[:limit]

    async def remove(self, notification_id: int) -> None:
        self.rows = [item for item in self.rows if item.id != notification_id]

    async def postpone(self, notification_id: int, next_attempt_at: datetime, reason: str) -> None:
        found = self.pending(notification_id)
        if found is not None:
            found.attempts += 1
            found.next_attempt_at = next_attempt_at
            found.last_error = reason

    async def mark_failed(self, notification_id: int, reason: str) -> None:
        found = self.pending(notification_id)
        if found is not None:
            found.status = OutboxStatus.FAILED
            found.last_error = reason


@dataclass
class FakeNotifications:
    """보낸 알림을 적어 두는 가짜 알림 서버. results 의 결과를 차례로 낸다. 다 쓰면 보냈다. 예외면 그것을 올린다."""

    results: list[Sent | Exception] = field(default_factory=list)
    sent: list[str] = field(default_factory=list)

    async def send(self, notification: OutgoingNotificationColumns) -> Sent:
        self.sent.append(notification.source_key)
        result = self.results.pop(0) if self.results else Sent(Delivery.DELIVERED)
        if isinstance(result, Exception):
            raise result
        return result


def dispatcher_of(
    store: FakeStore, notifications: FakeNotifications | None, now: datetime = NOW
) -> NotificationDispatcher:
    """가짜 발송함과 알림 서버, 정해진 시계로 도는 보내는 작업."""
    return NotificationDispatcher(store=store, notifications=lambda: notifications, clock=lambda: now)


# --- 칸 ---


def test_the_columns_make_a_table_with_named_constraints():
    table = OutgoingNotification.__table__
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))

    assert table.name == 'outgoing_notifications'
    assert "CONSTRAINT ck_outgoing_notifications_status_allowed CHECK (status IN ('pending', 'failed'))" in ddl
    assert 'CONSTRAINT ck_outgoing_notifications_attempts_not_negative CHECK (attempts >= 0)' in ddl
    assert 'CONSTRAINT uq_outgoing_notifications_source_key UNIQUE (source_key)' in ddl
    assert 'payload JSONB NOT NULL' in ddl


def test_the_due_index_holds_only_waiting_rows():
    (index,) = OutgoingNotification.__table__.indexes
    ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert ddl.endswith("ON outgoing_notifications (next_attempt_at) WHERE status = 'pending'")


def test_each_server_gets_its_own_constraints():
    class Other(DeclarativeBase):
        metadata = MetaData(naming_convention=NAMING_CONVENTION)

    class OtherNotification(OutgoingNotificationColumns, Other):
        pass

    # 같은 제약 객체를 두 표에 걸면 SQLAlchemy 가 거절한다. 표마다 새로 만든다
    assert OtherNotification.__table__.constraints.isdisjoint(OutgoingNotification.__table__.constraints)


# --- 알림 서버를 부르는 것 ---


def mock_client(handler) -> httpx.AsyncClient:
    """handler 가 답하는 httpx 클라이언트."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def http_notifications(handler, source: str = 'asset') -> HttpNotifications:
    """가짜 알림 서버를 부르는 것. 서명의 시각은 고정한다."""
    return HttpNotifications(
        mock_client(handler), BASE_URL + '/', source, SecretStr(SECRET), timeout=1, clock=lambda: 1_700_000_000
    )


def test_the_address_carries_the_server_name():
    assert put_path('asset') == '/api/v1/notification/service/asset/notifications'
    assert put_path('chat') == '/api/v1/notification/service/chat/notifications'


async def test_the_request_is_signed_like_the_notification_server_expects():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={'id': 1, 'status': 'created'})

    sent = await http_notifications(handler, 'chat').send(row('character.hidden:c1:3'))

    (request,) = seen
    path = '/api/v1/notification/service/chat/notifications'
    assert sent == Sent(Delivery.DELIVERED)
    assert str(request.url) == BASE_URL + path
    assert json.loads(request.content) == {
        'source_key': 'character.hidden:c1:3',
        'user_id': str(USER),
        'kind': 'character.hidden',
        'payload': {'character_id': 'c1', 'name': '렌'},
    }
    # 알림 서버가 확인하는 그대로 다시 계산해 본다(notification-server 의 서명 확인)
    content = f'1700000000.POST\n{path}\n'.encode() + request.content
    digest = hmac.new(SECRET.encode(), content, hashlib.sha256).hexdigest()
    assert request.headers['X-Service-Signature'] == f't=1700000000,v1={digest}'


def test_the_body_is_compact_utf8():
    # 보낸 바이트에 서명한다. 빈칸을 넣지 않고 한글을 그대로 둔다
    body = encode(row('a'))
    assert '렌'.encode() in body
    assert b': ' not in body


@pytest.mark.parametrize(
    ('status_code', 'expected'),
    [
        (201, Sent(Delivery.DELIVERED)),
        (200, Sent(Delivery.DELIVERED)),
        (401, Sent(Delivery.UNAVAILABLE, 'unauthorized')),
        (408, Sent(Delivery.UNAVAILABLE, 'status_408')),
        (429, Sent(Delivery.UNAVAILABLE, 'status_429')),
        (500, Sent(Delivery.UNAVAILABLE, 'status_500')),
        (503, Sent(Delivery.UNAVAILABLE, 'status_503')),
        (409, Sent(Delivery.REJECTED, 'status_409')),
        (413, Sent(Delivery.REJECTED, 'status_413')),
        (422, Sent(Delivery.REJECTED, 'status_422')),
        (404, Sent(Delivery.REJECTED, 'status_404')),
    ],
)
async def test_the_answer_decides_what_happens_next(status_code: int, expected: Sent):
    sent = await http_notifications(lambda request: httpx.Response(status_code)).send(row('a'))

    assert sent == expected


@pytest.mark.parametrize(
    ('error', 'reason'),
    [(httpx.ReadTimeout('slow'), 'timeout'), (httpx.ConnectError('refused'), 'unreachable')],
)
async def test_no_answer_is_sent_again(error: Exception, reason: str):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    assert await http_notifications(handler).send(row('a')) == Sent(Delivery.UNAVAILABLE, reason)


# --- 보내는 작업 ---


async def test_a_delivered_notification_leaves_the_outbox():
    store = FakeStore([row('a')])
    fake = FakeNotifications()

    dispatched = await dispatcher_of(store, fake).tick()

    assert fake.sent == ['a']
    assert (dispatched.sent, dispatched.busy()) == (1, True)
    assert store.rows == []


async def test_an_unavailable_server_is_tried_again_later():
    store = FakeStore([row('a')])
    fake = FakeNotifications([Sent(Delivery.UNAVAILABLE, 'status_503')])

    assert (await dispatcher_of(store, fake).tick()).retried == 1
    (waiting,) = store.rows
    assert (waiting.status, waiting.attempts, waiting.last_error) == (OutboxStatus.PENDING, 1, 'status_503')
    assert waiting.next_attempt_at == NOW + timedelta(seconds=10)

    # 기다리는 동안은 보내지 않는다. 지나면 다시 보낸다
    await dispatcher_of(store, fake, NOW + timedelta(seconds=9)).tick()
    await dispatcher_of(store, fake, NOW + timedelta(seconds=10)).tick()
    assert fake.sent == ['a', 'a']
    assert store.rows == []


async def test_a_second_miss_waits_twice_as_long():
    store = FakeStore([row('a', attempts=1)])

    await dispatcher_of(store, FakeNotifications([Sent(Delivery.UNAVAILABLE, 'timeout')])).tick()

    assert store.rows[0].next_attempt_at == NOW + timedelta(seconds=20)


@pytest.mark.parametrize(
    ('attempts', 'seconds'), [(0, 10), (1, 10), (2, 20), (3, 40), (9, 2560), (10, 3600), (30, 3600)]
)
def test_the_wait_doubles_up_to_an_hour(attempts: int, seconds: int):
    assert retry_delay(attempts) == timedelta(seconds=seconds)


async def test_a_rejected_notification_is_kept_as_failed():
    store = FakeStore([row('a')])
    fake = FakeNotifications([Sent(Delivery.REJECTED, 'status_409')])

    assert (await dispatcher_of(store, fake).tick()).rejected == 1
    await dispatcher_of(store, fake, NOW + timedelta(days=1)).tick()

    # 버그다. 사람이 보도록 남기고 다시 보내지 않는다
    (failed,) = store.rows
    assert (failed.status, failed.last_error) == (OutboxStatus.FAILED, 'status_409')
    assert fake.sent == ['a']


async def test_without_an_address_nothing_is_sent():
    store = FakeStore([row('a')])

    dispatched = await dispatcher_of(store, None).tick()

    # 주소를 비우면 적기만 한다
    assert dispatched.busy() is False
    assert store.limits == []
    assert len(store.rows) == 1


async def test_old_unsent_notifications_are_dropped():
    old = NOW - STALE_AFTER - timedelta(minutes=1)
    store = FakeStore(
        [
            row('old', 1, created_at=old),
            row('old-failed', 2, created_at=old, status=OutboxStatus.FAILED),
            row('edge', 3, created_at=NOW - STALE_AFTER),
        ]
    )

    dispatched = await dispatcher_of(store, None).tick()

    # 주소가 없어도 지운다. 받지 않은 것(failed)은 사람이 볼 때까지 남긴다. 딱 7일 된 것은 남는다
    assert dispatched.dropped == 1
    assert [item.source_key for item in store.rows] == ['old-failed', 'edge']


async def test_one_broken_notification_does_not_stop_the_others(caplog: pytest.LogCaptureFixture):
    store = FakeStore([row('a', 1), row('b', 2)])
    fake = FakeNotifications([RuntimeError('boom')])

    with caplog.at_level(logging.ERROR, logger=dispatching.__name__):
        dispatched = await dispatcher_of(store, fake).tick()

    assert (dispatched.failed, dispatched.sent) == (1, 1)
    # 예외가 난 알림은 그대로 남아 다음 바퀴에 다시 보낸다
    assert [item.source_key for item in store.rows] == ['a']
    (record,) = caplog.records
    assert (record.error_code, record.kind, record.notification_id) == ('job.failed', 'character.hidden', 1)


async def test_a_batch_is_limited(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dispatching, 'DISPATCH_BATCH', 2)
    store = FakeStore([row('a', 1), row('b', 2), row('c', 3)])
    fake = FakeNotifications()

    await dispatcher_of(store, fake).tick()

    # 먼저 적은 것부터 보낸다. 남은 것은 다음 바퀴다
    assert store.limits == [2]
    assert fake.sent == ['a', 'b']


async def test_a_late_result_does_not_revive_a_sent_notification():
    notification = row('a')
    store = FakeStore([notification])
    first = dispatcher_of(store, FakeNotifications())
    late = FakeNotifications([Sent(Delivery.UNAVAILABLE, 'timeout')])

    # 한 서버가 보내 지운 뒤에, 같은 줄을 늦게 본 다른 서버가 "다시 보낼 일"을 적는다
    await first.tick()
    await first.deliver(late, notification, NOW)

    assert store.rows == []


# --- 로그 ---


@pytest.mark.parametrize(
    ('sent', 'level', 'error_code'),
    [
        (Sent(Delivery.UNAVAILABLE, 'status_503'), logging.WARNING, UNAVAILABLE_ERROR_CODE),
        (Sent(Delivery.UNAVAILABLE, 'unauthorized'), logging.ERROR, UNAVAILABLE_ERROR_CODE),
        (Sent(Delivery.REJECTED, 'status_422'), logging.ERROR, REJECTED_ERROR_CODE),
    ],
)
async def test_an_unsent_notification_leaves_one_line_without_the_person(
    caplog: pytest.LogCaptureFixture, sent: Sent, level: int, error_code: str
):
    store = FakeStore([row('a', 9)])

    with caplog.at_level(logging.WARNING, logger=dispatching.__name__):
        await dispatcher_of(store, FakeNotifications([sent])).tick()

    (record,) = caplog.records
    assert (record.levelno, record.error_code, record.reason) == (level, error_code, sent.reason)
    assert (record.operation, record.kind, record.notification_id) == (DISPATCH_OPERATION, 'character.hidden', 9)
    assert record.result == ('client_error' if sent.delivery == Delivery.REJECTED else 'server_error')
    # 받는 사람과 알림의 내용은 남기지 않는다
    assert str(USER) not in str(record.__dict__)
    assert '렌' not in str(record.__dict__)


async def test_a_busy_round_is_logged_at_info(caplog: pytest.LogCaptureFixture):
    store = FakeStore([row('a')])

    with caplog.at_level(logging.DEBUG, logger=dispatching.__name__):
        await dispatcher_of(store, FakeNotifications()).tick()
        await dispatcher_of(store, FakeNotifications()).tick()

    busy, quiet = caplog.records
    assert (busy.levelno, busy.sent, busy.operation, busy.result) == (logging.INFO, 1, DISPATCH_OPERATION, 'success')
    assert busy.duration_ms >= 0
    assert quiet.levelno == logging.DEBUG


# --- 도는 것 ---


@dataclass
class BrokenStore(FakeStore):
    """DB 가 없는 것처럼 찾을 때마다 실패하는 발송함."""

    rounds: int = 0

    async def drop_stale(self, cutoff: datetime) -> int:
        self.rounds += 1
        raise RuntimeError('db down')


async def test_the_loop_keeps_running_after_a_failed_round(caplog: pytest.LogCaptureFixture):
    store = BrokenStore()
    looping = replace(dispatcher_of(store, None), interval=0)

    with caplog.at_level(logging.ERROR, logger=dispatching.__name__):
        running = dispatching.start(looping)
        while store.rounds < 2:
            await asyncio.sleep(0)
        await asyncio.wait_for(running.halt(), timeout=1)

    # 한 바퀴가 통째로 실패해도(DB 가 없다) 멈추지 않고 다음 바퀴를 돈다
    assert running.task.done()
    assert running.task.get_name() == 'notification-dispatcher'
    assert caplog.records
    assert all(record.error_code == 'job.failed' for record in caplog.records)


# --- 설정 ---


class SenderSettings(TestSettings, NotificationSettings):
    """알림을 보내는 서버의 설정과 같은 모양."""

    __test__ = False
    service_name: ClassVar[str] = 'sender-test'


def sender_settings(**overrides) -> SenderSettings:
    """알림을 보내는 서버의 설정. 개발자의 .env 는 읽지 않는다."""
    values = {
        'log_level': 'warning',
        'database_url': 'postgresql+asyncpg://core:pw@127.0.0.1:5432/trpg',
        'auth_jwks_url': TEST_JWKS_URL,
        'otel_exporter_otlp_endpoint': '',
    }
    return SenderSettings(_env_file=None, **{**values, **overrides})


def test_the_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('NOTIFICATION_URL', BASE_URL)
    monkeypatch.setenv('NOTIFICATION_SECRET', SECRET)
    monkeypatch.setenv('NOTIFICATION_TIMEOUT_SECONDS', '2')

    settings = sender_settings()

    assert (settings.notification_url, settings.notification_timeout_seconds) == (BASE_URL, 2)
    assert settings.notification_secret.get_secret_value() == SECRET


def test_the_address_needs_a_long_secret():
    with pytest.raises(ValidationError, match='NOTIFICATION_SECRET'):
        sender_settings(notification_url=BASE_URL, notification_secret='short')
    with pytest.raises(ValidationError, match='NOTIFICATION_SECRET'):
        sender_settings(notification_url=BASE_URL)
    # 주소가 없으면 비밀이 없어도 뜬다(적기만 한다)
    assert sender_settings(notification_url='  ').notification_url == '  '


def test_without_an_address_nothing_calls_the_server():
    assert build_notifications(sender_settings(notification_url='  '), httpx.AsyncClient(), 'asset') is None


def test_with_an_address_the_server_is_called():
    settings = sender_settings(notification_url=BASE_URL, notification_secret=SECRET, notification_timeout_seconds=2)

    built = build_notifications(settings, httpx.AsyncClient(), 'asset')

    assert isinstance(built, HttpNotifications)
    assert (built.base_url, built.source, built.timeout) == (BASE_URL, 'asset', 2)
    assert built.secret.get_secret_value() == SECRET


def test_the_clock_is_utc():
    assert dispatching.now_utc().tzinfo is UTC
