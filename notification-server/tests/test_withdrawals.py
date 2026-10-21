# notification-server/tests/test_withdrawals.py

"""
인증 서버가 탈퇴를 알리는 API(POST /api/v1/notification/service/users/{user_id}/withdrawal)를 검증한다(#603).

  - 인증 서버의 서명이 맞으면 그 사람의 알림(읽은 것, 읽지 않은 것)과 끈 종류를 지우고 200 processed 다
  - 다른 사람의 것은 그대로다. 몇 번을 받아도, 모르는 사람이어도 200 이다
  - 알림을 넣는 서버의 비밀, 서명 없음, 비어 있는 비밀은 401 이다. 지우지 않는다
  - 서명을 확인한 뒤에 본문을 본다. 모양이 틀리면 422 다
"""

import logging
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.logs import rendered
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import create_app
from app.notifications.models import Notification, NotificationMute
from app.withdrawals.router import WITHDRAWAL_OPERATION
from tests.conftest import make_client, make_test_settings
from tests.signing import TEST_AUTH_SECRET, TEST_SECRETS, encode, signed_put, signed_withdrawal, withdrawal_path

pytestmark = pytest.mark.usefixtures('clean_tables')

LEAVING = uuid.UUID('6f1e2d3c-4b5a-4c6d-8e7f-0a1b2c3d4e5f')
STAYING = uuid.UUID('1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d')
# 인증 서버가 보내는 본문(auth-server/accounts/withdrawal_client.py 의 isoformat)
BODY = {'withdrawn_at': '2026-10-28T03:00:00.123456+00:00'}
NOW = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)


async def seed(session: AsyncSession, user_id: uuid.UUID, *, read: bool) -> None:
    """그 사람의 알림 둘(하나는 읽음 여부를 정한다)과 끈 종류 하나를 넣는다."""
    tag = user_id.hex[:8]
    session.add_all(
        [
            Notification(
                user_id=user_id,
                source='billing',
                source_key=f'order.paid:{tag}',
                kind='order.paid',
                payload={'order_id': tag},
                created_at=NOW,
                read_at=NOW if read else None,
            ),
            Notification(
                user_id=user_id,
                source='board',
                source_key=f'post.commented:{tag}',
                kind='post.commented',
                payload={'post_id': tag},
                created_at=NOW,
            ),
            NotificationMute(user_id=user_id, kind='post.commented', created_at=NOW),
        ]
    )
    await session.commit()


async def count(session: AsyncSession, model: type, user_id: uuid.UUID) -> int:
    """그 사람의 줄의 수."""
    return await session.scalar(select(func.count()).select_from(model).where(model.user_id == user_id))


async def remaining(session: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """그 사람의 알림과 끈 종류의 수. 앱이 다른 세션에서 지웠으므로 새로 읽는다."""
    session.expire_all()
    return await count(session, Notification, user_id), await count(session, NotificationMute, user_id)


# --- 지우기 ---


async def test_a_withdrawal_erases_the_inbox_and_the_mutes(client: AsyncClient, session: AsyncSession):
    await seed(session, LEAVING, read=True)

    response = await signed_withdrawal(client, str(LEAVING), BODY)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'processed'}
    assert await remaining(session, LEAVING) == (0, 0)


async def test_other_people_are_left_alone(client: AsyncClient, session: AsyncSession):
    await seed(session, LEAVING, read=False)
    await seed(session, STAYING, read=False)

    await signed_withdrawal(client, str(LEAVING), BODY)

    assert await remaining(session, STAYING) == (2, 1)


async def test_the_same_withdrawal_again_is_still_processed(client: AsyncClient, session: AsyncSession):
    # 인증 서버가 답을 못 받아 다시 보낸 것이다
    await seed(session, LEAVING, read=False)
    await signed_withdrawal(client, str(LEAVING), BODY)

    again = await signed_withdrawal(client, str(LEAVING), BODY)

    assert again.status_code == status.HTTP_200_OK
    assert again.json() == {'status': 'processed'}


async def test_an_unknown_person_is_processed_too(client: AsyncClient):
    response = await signed_withdrawal(client, str(uuid.uuid4()), BODY)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'processed'}


async def test_the_counts_are_logged_without_the_person(client: AsyncClient, session: AsyncSession, caplog):
    await seed(session, LEAVING, read=True)

    with caplog.at_level(logging.INFO, logger='app.withdrawals.router'):
        await signed_withdrawal(client, str(LEAVING), BODY)

    (entry,) = rendered(caplog.records, 'app.withdrawals.router')
    assert entry['operation'] == WITHDRAWAL_OPERATION
    assert (entry['deleted_notifications'], entry['deleted_mutes']) == (2, 1)
    assert str(LEAVING) not in str(entry) and LEAVING.hex not in str(entry)


# --- 서명 ---


async def test_a_notifying_server_cannot_report_a_withdrawal(client: AsyncClient, session: AsyncSession):
    await seed(session, LEAVING, read=False)

    response = await signed_withdrawal(client, str(LEAVING), BODY, secret=TEST_SECRETS['billing'])

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await remaining(session, LEAVING) == (2, 1)


async def test_an_unsigned_withdrawal_is_refused(client: AsyncClient, session: AsyncSession):
    await seed(session, LEAVING, read=False)

    response = await client.post(
        withdrawal_path(str(LEAVING)), content=encode(BODY), headers={'Content-Type': 'application/json'}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await remaining(session, LEAVING) == (2, 1)


async def test_without_the_auth_server_secret_nothing_is_accepted(engine: AsyncEngine, session: AsyncSession):
    # 비밀을 아직 적지 않았다. 인증 서버는 비밀을 적은 뒤에 쌓인 것부터 다시 보낸다
    await seed(session, LEAVING, read=False)
    app: FastAPI = create_app(make_test_settings(auth_server_secret=''), engine=engine)

    # 다른 서버의 비밀로 바꿔 받지도 않는다
    secrets = [TEST_AUTH_SECRET, *TEST_SECRETS.values()]
    async with make_client(app) as client:
        codes = [(await signed_withdrawal(client, str(LEAVING), BODY, secret=secret)).status_code for secret in secrets]
    await app.state.http_client.aclose()

    assert codes == [status.HTTP_401_UNAUTHORIZED] * len(secrets)
    assert await remaining(session, LEAVING) == (2, 1)


async def test_the_auth_server_secret_cannot_put_notifications(client: AsyncClient):
    # 인증 서버는 알림을 넣지 않는다. 그 비밀로 넣는 주소를 불러도 401 이다
    body = {'source_key': 'x:1', 'user_id': str(LEAVING), 'kind': 'order.paid', 'payload': {}}
    response = await signed_put(client, body, source='billing', secret=TEST_AUTH_SECRET)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 본문과 주소 ---


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'withdrawn_at': None},
        {'withdrawn_at': '어제'},
        # 시간대가 없는 시각은 받지 않는다. 인증 서버는 늘 시간대를 붙인다
        {'withdrawn_at': '2026-10-28T03:00:00'},
        {**BODY, 'email': 'someone@example.com'},
    ],
)
async def test_a_malformed_body_is_refused(client: AsyncClient, session: AsyncSession, body: dict):
    await seed(session, LEAVING, read=False)

    response = await signed_withdrawal(client, str(LEAVING), body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await remaining(session, LEAVING) == (2, 1)


async def test_a_malformed_person_is_refused(client: AsyncClient):
    response = await signed_withdrawal(client, 'not-a-uuid', BODY)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
