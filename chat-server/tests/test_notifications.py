# chat-server/tests/test_notifications.py

"""
운영자가 대화 속 답의 신고를 처리한 것을 알리는 것(app/notifications/, #678)을 검증한다. 실제 DB(chat_test)에서 돈다.
발송함의 쿼리와 보내는 작업의 규칙은 공용 코드와 asset 서버의 테스트가 본다. 여기서는 chat 의 몫만 본다.

보는 것.
  - 처리하면(받아들이든 아니든) 신고한 사람에게 message_report.handled 하나. 결과, 사유, 대화의 글은 싣지 않는다
  - 이미 처리한 신고와 없는 신고는 알리지 않는다
  - 탈퇴하면 그 사람에게 보내지 않은 알림을 지운다
  - 서버가 뜨면 보내는 작업이 돌고, 실제 발송함에서 보낸 것을 지운다. 테스트는 보내지 않는다(주소가 비었다)
"""

import asyncio
import uuid
from dataclasses import dataclass, field, replace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.database import create_engine
from server_core.notifications.client import Delivery, HttpNotifications, Sent
from server_core.notifications.models import OutgoingNotificationColumns
from server_core.testing.tokens import FakeAuthServer, SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.main import API_PREFIX, create_app
from app.notifications import outbox
from app.notifications.models import OutgoingNotification
from app.reports.models import MessageReport
from tests.assets import FakeAsset
from tests.conftest import make_client, make_test_settings
from tests.models import FakeRouter, ScriptedProvider
from tests.test_message_reports_api import messages, report, say, start
from tests.test_withdrawal import notify
from tests.turns import ME, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

ADMIN_URL = f'{API_PREFIX}/admin'
OPERATOR = uuid.UUID('22222222-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
SECRET = 'c' * 40


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def operator(signing_key: SigningKey) -> dict[str, str]:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
async def reported(client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict) -> str:
    """캐릭터의 답 하나를 신고한 것. 신고의 id."""
    app.state.model_router = FakeRouter(ScriptedProvider(pieces=['위험한 답.']))
    conversation = await start(client, session, asset, mine)
    await say(client, app, mine, conversation, '안녕')
    path = await messages(client, mine, conversation)
    response = await report(client, mine, path[-1])
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


async def handle(client: AsyncClient, operator: dict, report_id: str, result: str = 'actioned'):
    body = {'outcome': result, 'reason': '운영자만 보는 사유'}
    return await client.put(f'{ADMIN_URL}/message-reports/{report_id}/outcome', json=body, headers=operator)


async def outgoing(session: AsyncSession) -> list[OutgoingNotification]:
    """발송함의 모든 줄. 적은 차례다. 세션이 기억한 것을 버리고 DB 에서 다시 읽는다."""
    session.expire_all()
    return list(await session.scalars(select(OutgoingNotification).order_by(OutgoingNotification.id)))


# --- 처리 ---


@pytest.mark.parametrize('result', ['actioned', 'dismissed'])
async def test_handling_tells_the_reporter_without_the_result(
    client: AsyncClient, session: AsyncSession, operator: dict, reported: str, result: str
):
    response = await handle(client, operator, reported, result)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    (notice,) = await outgoing(session)
    name = await session.scalar(select(MessageReport.character_name))
    assert (notice.user_id, notice.kind) == (ME, 'message_report.handled')
    assert notice.source_key == f'message_report.handled:{reported}'
    # 결과도 사유도 대화의 글도 싣지 않는다. 신고한 때의 캐릭터 이름만 있다
    assert notice.payload == {'name': name}


async def test_handling_again_or_a_missing_report_tells_nobody_more(
    client: AsyncClient, session: AsyncSession, operator: dict, reported: str
):
    await handle(client, operator, reported)

    again = await handle(client, operator, reported, 'dismissed')
    missing = await handle(client, operator, str(uuid.uuid4()))

    assert (again.status_code, missing.status_code) == (status.HTTP_409_CONFLICT, status.HTTP_404_NOT_FOUND)
    assert len(await outgoing(session)) == 1


# --- 탈퇴 ---


async def test_withdrawal_drops_what_was_not_sent(client: AsyncClient, session: AsyncSession):
    for user_id, key in ((ME, 'mine'), (OTHER, 'theirs')):
        outbox.put(session, user_id, outbox.REPORT_HANDLED, key, {'name': '세라'})
    await session.commit()

    response = await notify(client, ME)

    assert response.status_code == status.HTTP_200_OK
    assert [notice.user_id for notice in await outgoing(session)] == [OTHER]


# --- 서버와 설정 ---


@dataclass
class FakeNotifications:
    """보낸 알림을 적어 두는 가짜 알림 서버. 늘 받는다."""

    sent: list[str] = field(default_factory=list)

    async def send(self, notification: OutgoingNotificationColumns) -> Sent:
        self.sent.append(notification.source_key)
        return Sent(Delivery.DELIVERED)


async def test_tests_do_not_send(app: FastAPI):
    # 테스트의 설정은 주소를 비운다(tests/conftest.py)
    assert app.state.notifications is None


def test_an_address_builds_a_signed_sender_as_chat(auth_server: FakeAuthServer):
    settings = make_test_settings(notification_url='http://notification.test', notification_secret=SECRET)

    built = create_app(settings, http_client=auth_server.make_client()).state.notifications

    assert isinstance(built, HttpNotifications)
    assert built.source == 'chat'


def test_an_address_needs_a_long_secret():
    with pytest.raises(ValidationError, match='NOTIFICATION_SECRET'):
        make_test_settings(notification_url='http://notification.test', notification_secret='short')


async def test_the_server_sends_from_the_real_outbox_while_it_is_up(
    auth_server: FakeAuthServer, settings: Settings, session: AsyncSession
):
    outbox.put(session, ME, outbox.REPORT_HANDLED, 'a', {'name': '세라'})
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

    # 뜨면 돌고, 보낸 줄은 발송함에서 지운다. 꺼지면 멈춘다
    assert fake.sent == ['a']
    assert await outgoing(session) == []
