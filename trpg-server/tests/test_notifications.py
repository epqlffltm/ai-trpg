# trpg-server/tests/test_notifications.py

"""
방장에게 보내는 알림(app/notifications/)을 검증한다.

보는 것.
  - 발송함에 적기: 서술 모델의 은퇴 셋(예정, 바꿈, 대신할 모델 없음)이 방장에게만, 이벤트마다 한 줄이다.
    열쇠는 "<kind>:<테이블>:<이벤트의 번호>" 라 은퇴 예정의 단계마다 다르다. 내용에 테이블의 ID 와 제목이 붙는다.
  - 알림 서버를 부르는 것: 이 서버의 이름(game)의 주소로 서명해 넣는다.
  - 보내는 작업: 이 서버의 발송함 표로 돈다(보내면 지운다, 늦게 본 서버가 지운 것을 되살리지 않는다).
  - 설정: 주소가 있으면 game 으로서 알림 서버를 부른다. 테스트는 보내지 않는다.

서명의 모양, 답의 뜻, 다시 보내는 간격, 오래된 것 지우기, 로그, 설정의 검사는 공용 코드의 테스트가 본다
(shared/server-core/tests/test_notifications.py, #589).
"""

import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from server_core.notifications.client import Delivery, HttpNotifications, Sent
from server_core.notifications.dispatcher import NotificationDispatcher
from server_core.notifications.setup import build_notifications
from server_core.service_auth.signing import SIGNATURE_HEADER
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.routing import utc_now
from app.catalog import service as catalog
from app.notifications import outbox
from app.notifications.models import OutboxStatus, OutgoingNotification
from tests.catalog_rows import retire
from tests.conftest import make_test_settings
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


def sample() -> OutgoingNotification:
    """발송함의 한 줄. DB 에 넣지 않는다."""
    return OutgoingNotification(
        id=7,
        source_key='narration_model.retiring:t:3',
        user_id=HOST,
        kind='narration_model.retiring',
        payload={'title': '추격전', 'days_left': 7},
    )


async def test_the_game_server_puts_into_its_own_address():
    # 알림 서버는 주소의 이름(game)으로 비밀(GAME_SERVER_SECRET)과 넣을 수 있는 종류를 정한다
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201)

    settings = make_test_settings(notification_url=BASE_URL, notification_secret=SECRET)
    built = build_notifications(settings, httpx.AsyncClient(transport=httpx.MockTransport(answer)), outbox.SOURCE)

    sent = await built.send(sample())

    assert sent == Sent(Delivery.DELIVERED)
    (request,) = seen
    assert request.url.path == '/api/v1/notification/service/game/notifications'
    assert request.headers[SIGNATURE_HEADER].startswith('t=')


# --- 보내는 작업 ---


async def test_a_delivered_notification_leaves_the_outbox(app: FastAPI, session: AsyncSession):
    await put(session, 'a')
    fake = FakeNotifications()

    dispatched = await dispatcher_of(app, fake).tick()

    assert fake.sent == ['a']
    assert (dispatched.sent, dispatched.busy()) == (1, True)
    assert await outgoing(session) == []


async def test_two_servers_sending_the_same_notification_do_not_revive_it(app: FastAPI, session: AsyncSession):
    notification = await put(session, 'a')
    first = dispatcher_of(app, FakeNotifications())
    late = FakeNotifications([Sent(Delivery.UNAVAILABLE, 'timeout')])

    # 한 서버가 보내 지운 뒤에, 같은 줄을 늦게 본 다른 서버가 "다시 보낼 일"을 적는다
    await first.tick()
    await first.deliver(late, notification, NOW)

    assert await outgoing(session) == []


# --- 설정 ---


def test_with_an_address_the_server_is_called():
    settings = make_test_settings(notification_url=BASE_URL, notification_secret=SECRET, notification_timeout_seconds=2)

    built = build_notifications(settings, httpx.AsyncClient(), outbox.SOURCE)

    assert isinstance(built, HttpNotifications)
    assert (built.base_url, built.secret.get_secret_value(), built.timeout) == (BASE_URL, SECRET, 2)
    assert built.source == 'game'


async def test_tests_do_not_send(app: FastAPI):
    # 테스트의 설정은 주소를 비운다(tests/conftest.py)
    assert app.state.notifications is None


async def test_the_outbox_keeps_one_row_per_key(session: AsyncSession):
    await put(session, 'a')
    outbox.put(session, GUEST, 'narration_model.retiring', 'a', {})

    # 같은 열쇠는 게임 서버 안에서도 하나다
    with pytest.raises(IntegrityError, match='uq_outgoing_notifications_source_key'):
        await session.commit()
