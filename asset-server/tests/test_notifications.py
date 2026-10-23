# asset-server/tests/test_notifications.py

"""
운영자의 조치를 알리는 것(app/notifications/, #678)과 발송함의 실제 쿼리를 검증한다. 실제 DB(asset_test)에서 돈다.
보내는 작업의 규칙(다시 보내기, 실패, 로그)은 공용 코드의 테스트가 DB 없이 본다(shared/server-core/tests).

보는 것.
  - 숨기면 주인에게 character.hidden, 풀면 character.unhidden. 숨김이 바뀌지 않으면 알리지 않는다
  - 신고를 처리하면(받아들이든 아니든) 신고한 사람마다 character_report.handled. 결과와 사유는 싣지 않는다
  - 조치가 실패하면(없는 캐릭터) 알림도 없다
  - 발송함의 실제 쿼리: 보내면 지우고, 못 보내면 미루고, 받지 않으면 실패로 둔다. 늦은 결과가 지운 줄을 살리지 않는다.
    오래된 것만 지운다. 열쇠는 하나다
  - 탈퇴하면 그 사람에게 보내지 않은 알림을 지운다
  - 서버가 뜨면 보내는 작업이 돈다. 테스트는 보내지 않는다(주소가 비었다)
"""

import asyncio
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.database import create_engine
from server_core.notifications import dispatcher as dispatching
from server_core.notifications.client import Delivery, HttpNotifications, Sent, put_path
from server_core.notifications.dispatcher import STALE_AFTER, NotificationDispatcher
from server_core.notifications.models import OutboxStatus, OutgoingNotificationColumns
from server_core.testing.tokens import FakeAuthServer, SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.main import API_PREFIX, create_app
from app.notifications import outbox
from app.notifications.models import OutgoingNotification
from app.operators.models import OperatorAction
from app.reports.models import CharacterReport
from tests.conftest import make_client, make_test_settings
from tests.signing import signed_withdrawal

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
LISTINGS_URL = f'{API_PREFIX}/listings/characters'
ADMIN_URL = f'{API_PREFIX}/admin'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
OWNER = uuid.UUID('22222222-2222-4333-8444-555555555555')
READERS = [uuid.UUID(f'{number}9999999-2222-4333-8444-555555555555') for number in range(1, 3)]
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}
NOW = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)
SECRET = 'a' * 40


@pytest.fixture
def settings() -> Settings:
    """누구나 캐릭터를 만들고 공개로 두는 설정. 주인과 운영자가 다른 사람이 되게 한다."""
    return make_test_settings(characters_for_everyone=True, public_for_everyone=True)


def headers_for(signing_key: SigningKey, user_id: uuid.UUID, operator: bool = False) -> dict:
    claims = make_access_claims(sub=str(user_id))
    if operator:
        claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    return headers_for(signing_key, OPERATOR, operator=True)


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return headers_for(signing_key, OWNER)


@pytest.fixture
def readers(signing_key: SigningKey) -> list[dict]:
    return [headers_for(signing_key, reader) for reader in READERS]


async def public_character(client: AsyncClient, headers: dict, name: str = '세라') -> dict:
    made = (await client.post(CHARACTERS_URL, json={'name': name, 'starts': [START]}, headers=headers)).json()
    await client.patch(f'{CHARACTERS_URL}/{made["id"]}', json={'visibility': 'public'}, headers=headers)
    await client.post(f'{CHARACTERS_URL}/{made["id"]}/versions', json={}, headers=headers)
    return made


async def report(client: AsyncClient, headers: dict, made: dict) -> None:
    body = {'reason': 'spam', 'description': '광고만 한다'}
    response = await client.post(f'{LISTINGS_URL}/{made["id"]}/reports', json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text


async def outcome(client: AsyncClient, headers: dict, made: dict, result: str):
    body = {'outcome': result, 'reason': '운영자만 보는 사유'}
    return await client.put(f'{ADMIN_URL}/characters/{made["id"]}/reports/outcome', json=body, headers=headers)


async def set_hidden(client: AsyncClient, headers: dict, made: dict, hidden: bool):
    body = {'hidden': hidden, 'reason': '운영자만 보는 사유'}
    return await client.put(f'{ADMIN_URL}/characters/{made["id"]}/hidden', json=body, headers=headers)


async def outgoing(session: AsyncSession) -> list[OutgoingNotification]:
    """발송함의 모든 줄. 적은 차례다. 세션이 기억한 것을 버리고 DB 에서 다시 읽는다."""
    session.expire_all()
    return list(await session.scalars(select(OutgoingNotification).order_by(OutgoingNotification.id)))


async def action_ids(session: AsyncSession) -> list[int]:
    """감사 기록의 번호들. 적은 차례다."""
    return list(await session.scalars(select(OperatorAction.id).order_by(OperatorAction.id)))


async def report_ids(session: AsyncSession) -> dict[uuid.UUID, uuid.UUID]:
    """신고한 사람마다 그 신고의 id."""
    rows = await session.execute(select(CharacterReport.reporter_id, CharacterReport.id))
    return {reporter_id: report_id for reporter_id, report_id in rows}


# --- 숨김과 풀기 ---


async def test_hiding_and_unhiding_tell_the_owner(
    client: AsyncClient, session: AsyncSession, operator: dict, owner: dict
):
    made = await public_character(client, owner)

    await set_hidden(client, operator, made, True)
    await set_hidden(client, operator, made, False)

    hidden, unhidden = await outgoing(session)
    first, second = await action_ids(session)
    payload = {'character_id': made['id'], 'name': '세라'}
    assert (hidden.user_id, hidden.kind, hidden.payload) == (OWNER, 'character.hidden', payload)
    assert (unhidden.user_id, unhidden.kind, unhidden.payload) == (OWNER, 'character.unhidden', payload)
    # 조치마다 열쇠가 다르다. 숨겼다 풀었다 다시 숨겨도 알림 서버가 앞의 것과 헷갈리지 않는다
    assert hidden.source_key == f'character.hidden:{made["id"]}:{first}'
    assert unhidden.source_key == f'character.unhidden:{made["id"]}:{second}'
    assert hidden.status == OutboxStatus.PENDING


async def test_nothing_is_told_when_the_hiding_does_not_change(
    client: AsyncClient, session: AsyncSession, operator: dict, owner: dict
):
    made = await public_character(client, owner)

    await set_hidden(client, operator, made, False)
    await set_hidden(client, operator, made, True)
    await set_hidden(client, operator, made, True)

    # 감사 기록은 조치마다 남지만, 알림은 숨김이 바뀐 한 번뿐이다
    assert len(await action_ids(session)) == 3
    assert [notice.kind for notice in await outgoing(session)] == ['character.hidden']


async def test_a_failed_action_tells_nobody(client: AsyncClient, session: AsyncSession, operator: dict):
    response = await set_hidden(client, operator, {'id': str(uuid.uuid4())}, True)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await outgoing(session) == []


# --- 신고의 처리 ---


async def test_actioning_tells_the_owner_and_each_reporter_without_the_result(
    client: AsyncClient, session: AsyncSession, operator: dict, owner: dict, readers: list[dict]
):
    made = await public_character(client, owner)
    for headers in readers:
        await report(client, headers, made)

    await outcome(client, operator, made, 'actioned')

    hidden, *handled = await outgoing(session)
    reports = await report_ids(session)
    assert (hidden.user_id, hidden.kind) == (OWNER, 'character.hidden')
    assert sorted((notice.user_id, notice.source_key) for notice in handled) == sorted(
        (reader, f'character_report.handled:{reports[reader]}') for reader in READERS
    )
    # 결과(숨김)도 사유도, 캐릭터의 id 도 싣지 않는다. 이름만 있다
    assert {notice.kind for notice in handled} == {'character_report.handled'}
    assert [notice.payload for notice in handled] == [{'name': '세라'}, {'name': '세라'}]


async def test_dismissing_tells_only_the_reporters(
    client: AsyncClient, session: AsyncSession, operator: dict, owner: dict, readers: list[dict]
):
    made = await public_character(client, owner)
    await report(client, readers[0], made)

    await outcome(client, operator, made, 'dismissed')

    (notice,) = await outgoing(session)
    assert (notice.user_id, notice.kind, notice.payload) == (READERS[0], 'character_report.handled', {'name': '세라'})


async def test_actioning_a_hidden_character_tells_only_the_reporters(
    client: AsyncClient, session: AsyncSession, operator: dict, owner: dict, readers: list[dict]
):
    made = await public_character(client, owner)
    await report(client, readers[0], made)
    await set_hidden(client, operator, made, True)

    await outcome(client, operator, made, 'actioned')

    # 이미 숨겨 있으니 주인에게 또 알리지 않는다
    kinds = [(notice.user_id, notice.kind) for notice in await outgoing(session)]
    assert kinds == [(OWNER, 'character.hidden'), (READERS[0], 'character_report.handled')]


# --- 발송함의 실제 쿼리 ---


def put(session: AsyncSession, key: str, user_id: uuid.UUID = OWNER) -> OutgoingNotification:
    """발송함에 한 줄을 올린다. 저장하지 않는다."""
    return outbox.put(session, user_id, 'character.hidden', key, {'character_id': 'c', 'name': '세라'})


@dataclass
class FakeNotifications:
    """보낸 알림을 적어 두는 가짜 알림 서버. results 의 결과를 차례로 낸다. 다 쓰면 보냈다."""

    results: list[Sent] = field(default_factory=list)
    sent: list[str] = field(default_factory=list)

    async def send(self, notification: OutgoingNotificationColumns) -> Sent:
        self.sent.append(notification.source_key)
        return self.results.pop(0) if self.results else Sent(Delivery.DELIVERED)


def dispatcher_of(app: FastAPI, notifications: FakeNotifications | None, now: datetime = NOW) -> NotificationDispatcher:
    """앱의 보내는 작업에 가짜 알림 서버와 시계를 꽂는다. 발송함은 앱의 실제 것이다."""
    app.state.notifications = notifications
    return replace(app.state.notification_dispatcher, clock=lambda: now)


async def test_the_real_outbox_removes_postpones_and_fails(app: FastAPI, session: AsyncSession):
    for key in ('sent', 'later', 'refused'):
        put(session, key)
    await session.commit()
    fake = FakeNotifications(
        [Sent(Delivery.DELIVERED), Sent(Delivery.UNAVAILABLE, 'status_503'), Sent(Delivery.REJECTED, 'status_422')]
    )

    dispatched = await dispatcher_of(app, fake).tick()

    later, refused = await outgoing(session)
    assert fake.sent == ['sent', 'later', 'refused']
    assert (dispatched.sent, dispatched.retried, dispatched.rejected) == (1, 1, 1)
    assert (later.status, later.attempts, later.last_error) == (OutboxStatus.PENDING, 1, 'status_503')
    assert later.next_attempt_at == NOW + timedelta(seconds=10)
    assert (refused.status, refused.last_error) == (OutboxStatus.FAILED, 'status_422')

    # 기다리는 동안은 찾지 않는다. 받지 않은 것은 다시 찾지 않는다
    waiting = FakeNotifications()
    await dispatcher_of(app, waiting, NOW + timedelta(seconds=9)).tick()
    await dispatcher_of(app, waiting, NOW + timedelta(seconds=10)).tick()
    assert waiting.sent == ['later']


async def test_the_real_outbox_sends_the_oldest_first(
    app: FastAPI, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(dispatching, 'DISPATCH_BATCH', 2)
    for key in ('a', 'b', 'c'):
        put(session, key)
        await session.commit()
    fake = FakeNotifications()

    await dispatcher_of(app, fake).tick()

    assert fake.sent == ['a', 'b']


async def test_a_late_result_does_not_revive_a_sent_row(app: FastAPI, session: AsyncSession):
    notification = put(session, 'a')
    await session.commit()
    first = dispatcher_of(app, FakeNotifications())

    # 한 서버가 보내 지운 뒤에, 같은 줄을 늦게 본 다른 서버가 "다시 보낼 일"과 "받지 않음"을 적는다
    await first.tick()
    await first.deliver(FakeNotifications([Sent(Delivery.UNAVAILABLE, 'timeout')]), notification, NOW)
    await first.deliver(FakeNotifications([Sent(Delivery.REJECTED, 'status_409')]), notification, NOW)

    assert await outgoing(session) == []


async def test_only_old_waiting_rows_are_dropped(app: FastAPI, session: AsyncSession):
    old = NOW - STALE_AFTER - timedelta(minutes=1)
    put(session, 'old').created_at = old
    failed = put(session, 'old-failed')
    failed.created_at, failed.status = old, OutboxStatus.FAILED
    put(session, 'fresh').created_at = NOW - timedelta(days=1)
    await session.commit()

    dispatched = await dispatcher_of(app, None).tick()

    assert dispatched.dropped == 1
    assert [notice.source_key for notice in await outgoing(session)] == ['old-failed', 'fresh']


async def test_one_row_per_key(session: AsyncSession):
    put(session, 'a')
    await session.commit()
    put(session, 'a', READERS[0])

    with pytest.raises(IntegrityError, match='uq_outgoing_notifications_source_key'):
        await session.commit()


# --- 탈퇴 ---


async def test_withdrawal_drops_what_was_not_sent(client: AsyncClient, session: AsyncSession):
    put(session, 'mine')
    put(session, 'theirs', READERS[0])
    await session.commit()

    response = await signed_withdrawal(client, str(OWNER))

    assert response.status_code == status.HTTP_200_OK
    assert [notice.user_id for notice in await outgoing(session)] == [READERS[0]]


# --- 서버와 설정 ---


async def test_tests_do_not_send(app: FastAPI):
    # 테스트의 설정은 주소를 비운다(tests/conftest.py)
    assert app.state.notifications is None


def test_an_address_builds_a_signed_sender_as_asset(auth_server: FakeAuthServer):
    settings = make_test_settings(notification_url='http://notification.test', notification_secret=SECRET)

    built = create_app(settings, http_client=auth_server.make_client()).state.notifications

    assert isinstance(built, HttpNotifications)
    assert (built.source, put_path(built.source)) == ('asset', '/api/v1/notification/service/asset/notifications')


def test_an_address_needs_a_long_secret():
    with pytest.raises(ValidationError, match='NOTIFICATION_SECRET'):
        make_test_settings(notification_url='http://notification.test', notification_secret='short')


async def test_the_server_runs_the_dispatcher_while_it_is_up(
    auth_server: FakeAuthServer, settings: Settings, session: AsyncSession
):
    put(session, 'a')
    await session.commit()
    # 꺼질 때 풀을 닫으므로 테스트 전체의 풀(engine)을 쓰지 않는다(tests/test_health.py 와 같다)
    app = create_app(settings, http_client=auth_server.make_client(), engine=create_engine(settings))
    fake = FakeNotifications()
    app.state.notifications = fake
    app.state.notification_dispatcher = replace(app.state.notification_dispatcher, interval=0.01)

    async with app.router.lifespan_context(app), make_client(app):
        for _ in range(200):
            if fake.sent:
                break
            await asyncio.sleep(0.01)

    # 뜨면 돌고, 꺼지면 멈춘다(lifespan 이 끝나도 남아 도는 작업이 없다)
    assert fake.sent == ['a']
    assert await outgoing(session) == []
