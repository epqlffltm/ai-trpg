# trpg-server/tests/test_notifications.py

"""
방장에게 보내는 알림(app/notifications/)을 검증한다.

보는 것.
  - 발송함에 적기: 서술 모델의 은퇴 셋(예정, 바꿈, 대신할 모델 없음)이 방장에게만, 이벤트마다 한 줄이다.
    열쇠는 "<kind>:<테이블>:<이벤트의 번호>" 라 은퇴 예정의 단계마다 다르다. 내용에 테이블의 ID 와 제목이 붙는다.
  - 알림 서버를 부르는 것: 본문, 서명, 답의 뜻(보냈다, 다시 보낼 일, 받지 않았다).
  - 보내는 작업: 보내면 지우고, 못 보내면 기다리는 시간을 늘려 다시 보내고, 받지 않으면 실패로 둔다.
    오래 못 보낸 것은 지운다. 주소가 없으면 보내지 않는다. 한 알림이 예외로 끝나도 다른 알림은 보낸다.
  - 설정: 주소를 적으면 비밀이 32자 이상이어야 한다.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.routing import utc_now
from app.catalog import service as catalog
from app.notifications import dispatcher as dispatching
from app.notifications import outbox
from app.notifications.client import PUT_PATH, Delivery, HttpNotifications, Sent, encode
from app.notifications.dispatcher import (
    DISPATCH_OPERATION,
    REJECTED_ERROR_CODE,
    STALE_AFTER,
    UNAVAILABLE_ERROR_CODE,
    NotificationDispatcher,
    retry_delay,
)
from app.notifications.models import OutboxStatus, OutgoingNotification
from app.notifications.setup import build_notifications
from tests.catalog_rows import retire
from tests.conftest import make_test_settings
from tests.signing import SigningKey
from tests.test_model_offers import LUNA, FixedPrices, add_enabled, book, on_sale
from tests.test_npc_actions import bearer
from tests.test_recommended_model import MINI
from tests.test_round_time_limit import start_with

pytestmark = pytest.mark.usefixtures('clean_tables')

HOST = uuid.UUID('11111111-2222-4333-8444-555555555555')
GUEST = uuid.UUID('22222222-2222-4333-8444-555555555555')
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
TODAY = NOW.date()
SECRET = 'n' * 40
BASE_URL = 'http://notification.test'


@pytest.fixture
def host(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, HOST)


@pytest.fixture
def guest(signing_key: SigningKey) -> dict[str, str]:
    """함께 앉은 사람."""
    return bearer(signing_key, GUEST)


@pytest.fixture
async def models(app: FastAPI, session: AsyncSession, clean_tables) -> None:
    """켜진 OpenAI 모델 둘(Luna, Mini). 대신 쓸 모델을 고르면 Mini 다(tests/test_model_retirement.py 와 같다)."""
    for data in (LUNA, MINI):
        await add_enabled(session, data)
    app.state.price_list = FixedPrices(book(on_sale('gpt-6-luna', '30'), on_sale('gpt-6-mini', '10')))
    app.dependency_overrides[utc_now] = lambda: NOW


async def watch(app: FastAPI, now: datetime) -> None:
    """그 시각에 은퇴 지켜보기가 한 바퀴 돈다."""
    app.state.retirement_watch = replace(app.state.retirement_watch, clock=lambda: now)
    await app.state.retirement_watch.tick()


async def outgoing(session: AsyncSession) -> list[OutgoingNotification]:
    """발송함의 모든 줄. 적은 차례다. 세션이 기억한 것을 버리고 DB 에서 다시 읽는다."""
    session.expire_all()
    return list(await session.scalars(select(OutgoingNotification).order_by(OutgoingNotification.id)))


async def put(session: AsyncSession, key: str, **values) -> OutgoingNotification:
    """발송함에 한 줄을 적고 저장한다. values 로 칸을 바꾼다(created_at 등)."""
    notification = outbox.put(session, HOST, 'narration_model.retiring', key, {'title': '추격전'})
    for name, value in values.items():
        setattr(notification, name, value)
    await session.commit()
    return notification


@dataclass
class FakeNotifications:
    """보낸 알림을 적어 두는 가짜 알림 서버. results 의 결과를 차례로 낸다. 다 쓰면 보냈다. 예외면 그것을 올린다."""

    results: list[Sent | Exception] = field(default_factory=list)
    sent: list[str] = field(default_factory=list)

    async def send(self, notification: OutgoingNotification) -> Sent:
        self.sent.append(notification.source_key)
        result = self.results.pop(0) if self.results else Sent(Delivery.DELIVERED)
        if isinstance(result, Exception):
            raise result
        return result


def dispatcher_of(app: FastAPI, notifications: FakeNotifications | None, now: datetime = NOW) -> NotificationDispatcher:
    """앱의 보내는 작업에 가짜 알림 서버와 시계를 꽂는다."""
    app.state.notifications = notifications
    return replace(app.state.notification_dispatcher, clock=lambda: now)


# --- 발송함에 적기 ---


@pytest.mark.usefixtures('models')
async def test_each_retirement_stage_is_one_notification_for_the_host(
    client: AsyncClient, app: FastAPI, session: AsyncSession, host
):
    table = await start_with(client, host, narration_model='gpt-6-luna')
    await retire(session, 'gpt-6-luna', TODAY + timedelta(days=20))

    await watch(app, NOW)
    await watch(app, NOW + timedelta(days=7))
    first, second = await outgoing(session)

    assert (first.user_id, first.kind, first.status) == (HOST, 'narration_model.retiring', OutboxStatus.PENDING)
    assert first.payload == {
        'table_id': table['id'],
        'title': table['title'],
        'narration_model': 'gpt-6-luna',
        'retires_on': '2026-11-07',
        'days_left': 20,
    }
    # 단계마다 이벤트의 번호가 달라 열쇠가 다르다. 같은 열쇠면 알림 서버가 두 번째를 409 로 거절한다
    assert first.source_key.startswith(f'narration_model.retiring:{table["id"]}:')
    assert first.source_key != second.source_key
    assert second.payload['days_left'] == 13


@pytest.mark.usefixtures('models')
async def test_a_replacement_is_told_to_the_host_only(
    client: AsyncClient, app: FastAPI, session: AsyncSession, host, guest
):
    table = await start_with(client, host, guest, narration_model='gpt-6-luna')
    await retire(session, 'gpt-6-luna', TODAY)

    await watch(app, NOW)
    (notice,) = await outgoing(session)

    # 모델을 바꿀 수 있는 사람이 방장이다. 앉은 사람은 테이블의 이벤트로 본다
    assert (notice.user_id, notice.kind) == (HOST, 'narration_model.replaced')
    assert notice.payload['from'] == 'gpt-6-luna'
    assert notice.payload['narration_model'] == 'gpt-6-mini'
    assert notice.payload['table_id'] == table['id']


@pytest.mark.usefixtures('models')
async def test_a_retired_model_without_a_replacement_is_told_once(
    client: AsyncClient, app: FastAPI, session: AsyncSession, host
):
    await start_with(client, host, narration_model='gpt-6-luna')
    await catalog.disable_model(session, 'gpt-6-mini')
    await retire(session, 'gpt-6-luna', TODAY)

    await watch(app, NOW)
    await watch(app, NOW + timedelta(hours=1))
    (notice,) = await outgoing(session)

    # 방장이 고를 때까지 서술이 막힌다. 셋 중 가장 급한 알림이다
    assert notice.kind == 'narration_model.unavailable'
    assert notice.payload['narration_model'] == 'gpt-6-luna'


# --- 알림 서버를 부르는 것 ---


def mock_client(handler) -> httpx.AsyncClient:
    """handler 가 답하는 httpx 클라이언트."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def http_notifications(handler) -> HttpNotifications:
    """가짜 알림 서버를 부르는 것. 서명의 시각은 고정한다."""
    return HttpNotifications(
        mock_client(handler), BASE_URL + '/', SecretStr(SECRET), timeout=1, clock=lambda: 1_700_000_000
    )


def sample() -> OutgoingNotification:
    """발송함의 한 줄. DB 에 넣지 않는다."""
    return OutgoingNotification(
        id=7,
        source_key='narration_model.retiring:t:3',
        user_id=HOST,
        kind='narration_model.retiring',
        payload={'title': '추격전', 'days_left': 7},
    )


async def test_the_request_is_signed_like_the_notification_server_expects():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={'id': 1, 'status': 'created'})

    sent = await http_notifications(handler).send(sample())

    (request,) = seen
    assert sent == Sent(Delivery.DELIVERED)
    assert str(request.url) == BASE_URL + PUT_PATH
    assert json.loads(request.content) == {
        'source_key': 'narration_model.retiring:t:3',
        'user_id': str(HOST),
        'kind': 'narration_model.retiring',
        'payload': {'title': '추격전', 'days_left': 7},
    }
    # 알림 서버가 확인하는 그대로 다시 계산해 본다(notification-server/app/service_auth/signing.py)
    content = f'1700000000.POST\n{PUT_PATH}\n'.encode() + request.content
    digest = hmac.new(SECRET.encode(), content, hashlib.sha256).hexdigest()
    assert request.headers['X-Service-Signature'] == f't=1700000000,v1={digest}'


def test_the_body_is_compact_utf8():
    # 보낸 바이트에 서명한다. 빈칸을 넣지 않고 한글을 그대로 둔다
    assert '추격전'.encode() in encode(sample())
    assert b': ' not in encode(sample())


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
    sent = await http_notifications(lambda request: httpx.Response(status_code)).send(sample())

    assert sent == expected


@pytest.mark.parametrize(
    ('error', 'reason'),
    [(httpx.ReadTimeout('slow'), 'timeout'), (httpx.ConnectError('refused'), 'unreachable')],
)
async def test_no_answer_is_sent_again(error: Exception, reason: str):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    assert await http_notifications(handler).send(sample()) == Sent(Delivery.UNAVAILABLE, reason)


# --- 보내는 작업 ---


async def test_a_delivered_notification_leaves_the_outbox(app: FastAPI, session: AsyncSession):
    await put(session, 'a')
    fake = FakeNotifications()

    dispatched = await dispatcher_of(app, fake).tick()

    assert fake.sent == ['a']
    assert (dispatched.sent, dispatched.busy()) == (1, True)
    assert await outgoing(session) == []


async def test_an_unavailable_server_is_tried_again_later(app: FastAPI, session: AsyncSession):
    await put(session, 'a')
    fake = FakeNotifications([Sent(Delivery.UNAVAILABLE, 'status_503')])

    assert (await dispatcher_of(app, fake).tick()).retried == 1
    (waiting,) = await outgoing(session)
    assert (waiting.status, waiting.attempts, waiting.last_error) == (OutboxStatus.PENDING, 1, 'status_503')
    assert waiting.next_attempt_at == NOW + timedelta(seconds=10)

    # 기다리는 동안은 보내지 않는다. 지나면 다시 보낸다
    await dispatcher_of(app, fake, NOW + timedelta(seconds=9)).tick()
    await dispatcher_of(app, fake, NOW + timedelta(seconds=10)).tick()
    assert fake.sent == ['a', 'a']
    assert await outgoing(session) == []


@pytest.mark.parametrize(
    ('attempts', 'seconds'), [(0, 10), (1, 10), (2, 20), (3, 40), (9, 2560), (10, 3600), (30, 3600)]
)
def test_the_wait_doubles_up_to_an_hour(attempts: int, seconds: int):
    assert retry_delay(attempts) == timedelta(seconds=seconds)


async def test_a_rejected_notification_is_kept_as_failed(app: FastAPI, session: AsyncSession):
    await put(session, 'a')
    fake = FakeNotifications([Sent(Delivery.REJECTED, 'status_409')])

    assert (await dispatcher_of(app, fake).tick()).rejected == 1
    await dispatcher_of(app, fake, NOW + timedelta(days=1)).tick()

    # 버그다. 사람이 보도록 남기고 다시 보내지 않는다
    (failed,) = await outgoing(session)
    assert (failed.status, failed.last_error) == (OutboxStatus.FAILED, 'status_409')
    assert fake.sent == ['a']


async def test_without_an_address_nothing_is_sent(app: FastAPI, session: AsyncSession):
    await put(session, 'a')

    dispatched = await dispatcher_of(app, None).tick()

    # 주소를 비우면 적기만 한다
    assert dispatched.busy() is False
    assert len(await outgoing(session)) == 1


async def test_old_unsent_notifications_are_dropped(app: FastAPI, session: AsyncSession):
    old = NOW - STALE_AFTER - timedelta(minutes=1)
    await put(session, 'old', created_at=old)
    await put(session, 'old-failed', created_at=old, status=OutboxStatus.FAILED)
    await put(session, 'fresh', created_at=NOW - timedelta(days=1))

    dispatched = await dispatcher_of(app, None).tick()

    # 주소가 없어도 지운다. 받지 않은 것(failed)은 사람이 볼 때까지 남긴다
    assert dispatched.dropped == 1
    assert [notification.source_key for notification in await outgoing(session)] == ['old-failed', 'fresh']


async def test_one_broken_notification_does_not_stop_the_others(
    app: FastAPI, session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    await put(session, 'a')
    await put(session, 'b')
    fake = FakeNotifications([RuntimeError('boom')])

    with caplog.at_level(logging.ERROR, logger=dispatching.__name__):
        dispatched = await dispatcher_of(app, fake).tick()

    assert (dispatched.failed, dispatched.sent) == (1, 1)
    # 예외가 난 알림은 그대로 남아 다음 바퀴에 다시 보낸다
    assert [notification.source_key for notification in await outgoing(session)] == ['a']
    assert any(record.error_code == 'job.failed' for record in caplog.records)


async def test_a_batch_is_limited(app: FastAPI, session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dispatching, 'DISPATCH_BATCH', 2)
    for key in ('a', 'b', 'c'):
        await put(session, key)
    fake = FakeNotifications()

    await dispatcher_of(app, fake).tick()

    # 먼저 적은 것부터 보낸다. 남은 것은 다음 바퀴다
    assert fake.sent == ['a', 'b']


async def test_two_servers_sending_the_same_notification_do_not_revive_it(app: FastAPI, session: AsyncSession):
    notification = await put(session, 'a')
    first = dispatcher_of(app, FakeNotifications())
    late = FakeNotifications([Sent(Delivery.UNAVAILABLE, 'timeout')])

    # 한 서버가 보내 지운 뒤에, 같은 줄을 늦게 본 다른 서버가 "다시 보낼 일"을 적는다
    await first.tick()
    await first.deliver(late, notification, NOW)

    assert await outgoing(session) == []


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
    app: FastAPI, session: AsyncSession, caplog: pytest.LogCaptureFixture, sent: Sent, level: int, error_code: str
):
    await put(session, 'a')

    with caplog.at_level(logging.WARNING, logger=dispatching.__name__):
        await dispatcher_of(app, FakeNotifications([sent])).tick()

    (record,) = caplog.records
    assert (record.levelno, record.error_code, record.reason) == (level, error_code, sent.reason)
    assert (record.operation, record.kind) == (DISPATCH_OPERATION, 'narration_model.retiring')
    # 받는 사람과 알림의 내용은 남기지 않는다
    assert str(HOST) not in str(record.__dict__)
    assert '추격전' not in str(record.__dict__)


async def test_a_busy_round_is_logged_at_info(app: FastAPI, session: AsyncSession, caplog: pytest.LogCaptureFixture):
    await put(session, 'a')

    with caplog.at_level(logging.DEBUG, logger=dispatching.__name__):
        await dispatcher_of(app, FakeNotifications()).tick()
        await dispatcher_of(app, FakeNotifications()).tick()

    busy, quiet = caplog.records
    assert (busy.levelno, busy.sent, busy.operation) == (logging.INFO, 1, DISPATCH_OPERATION)
    assert quiet.levelno == logging.DEBUG


# --- 도는 것 ---


async def test_the_loop_keeps_running_after_a_failed_round(app: FastAPI, caplog: pytest.LogCaptureFixture):
    rounds = 0

    def broken_session():
        nonlocal rounds
        rounds += 1
        raise RuntimeError('db down')

    looping = replace(dispatcher_of(app, None), session_factory=broken_session, interval=0)

    with caplog.at_level(logging.ERROR, logger=dispatching.__name__):
        running = dispatching.start(looping)
        while rounds < 2:
            await asyncio.sleep(0)
        await asyncio.wait_for(running.halt(), timeout=1)

    # 한 바퀴가 통째로 실패해도(DB 가 없다) 멈추지 않고 다음 바퀴를 돈다
    assert running.task.done()
    assert caplog.records
    assert all(record.error_code == 'job.failed' for record in caplog.records)


# --- 설정 ---


def test_the_address_needs_a_long_secret():
    with pytest.raises(ValidationError, match='NOTIFICATION_SECRET'):
        make_test_settings(notification_url=BASE_URL, notification_secret='short')
    with pytest.raises(ValidationError, match='NOTIFICATION_SECRET'):
        make_test_settings(notification_url=BASE_URL)


def test_without_an_address_nothing_calls_the_server():
    settings = make_test_settings(notification_url='  ')

    assert build_notifications(settings, httpx.AsyncClient()) is None


def test_with_an_address_the_server_is_called():
    settings = make_test_settings(notification_url=BASE_URL, notification_secret=SECRET, notification_timeout_seconds=2)

    built = build_notifications(settings, httpx.AsyncClient())

    assert isinstance(built, HttpNotifications)
    assert (built.base_url, built.secret.get_secret_value(), built.timeout) == (BASE_URL, SECRET, 2)


async def test_tests_do_not_send(app: FastAPI):
    # 테스트의 설정은 주소를 비운다(tests/conftest.py)
    assert app.state.notifications is None


async def test_the_outbox_keeps_one_row_per_key(session: AsyncSession):
    await put(session, 'a')
    outbox.put(session, GUEST, 'narration_model.retiring', 'a', {})

    # 같은 열쇠는 게임 서버 안에서도 하나다
    with pytest.raises(IntegrityError, match='uq_outgoing_notifications_source_key'):
        await session.commit()
