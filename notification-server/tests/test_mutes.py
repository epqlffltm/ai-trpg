# notification-server/tests/test_mutes.py

"""
알림 끄기(#525)를 검증한다. 사용자가 종류별로 끄고 켜는 API(/api/v1/notification/me/notifications/mutes)와,
끈 종류의 알림을 넣을 때 거르는 것이다.

  - 끌 수 있는 종류마다 껐는지 보인다. 끄기와 켜기는 몇 번 해도 같다
  - 끌 수 없는 종류(결제, 제재)와 표에 없는 종류는 422 다
  - 끈 종류의 알림은 적지 않고, 넣는 서버에는 200(muted)으로 답한다. 다른 사람과 다른 종류는 그대로다
  - 다시 켜면 그 뒤의 알림부터 들어온다. 꺼 둔 동안의 것은 없다
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.notifications.catalog import mutable_kinds
from app.notifications.models import Notification, NotificationMute
from tests.metrics import MetricsRecorder
from tests.signing import signed_put
from tests.tokens import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

MUTES_URL = f'{API_PREFIX}/me/notifications/mutes'
ME = uuid.UUID('0b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
OTHER = uuid.UUID('b1c2d3e4-f5a6-4b7c-8d9e-0f1a2b3c4d5e')

# 게시판 서버가 넣는 댓글 알림의 값. 끌 수 있는 종류다
COMMENTED = {'board_slug': 'free', 'post_id': '7', 'post_title': '첫 글', 'comment_id': '11'}
# 결제 서버가 넣는 결제 알림의 값. 끌 수 없는 종류다
PAID = {'order_id': 'o-1', 'product_id': 'credits-1000', 'price': 1000, 'credits': '1000'}


@pytest.fixture
def my_headers(signing_key: SigningKey) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(ME)))}'}


@pytest.fixture
def other_headers(signing_key: SigningKey) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(OTHER)))}'}


def muted_kinds(response_body: dict) -> set[str]:
    """설정의 답에서 껐다고 한 종류들."""
    return {item['kind'] for item in response_body['kinds'] if item['muted']}


def commented(key: str, user_id: uuid.UUID = ME) -> dict:
    """게시판 서버가 보낼 댓글 알림 하나."""
    return {'source_key': key, 'user_id': str(user_id), 'kind': 'post.commented', 'payload': COMMENTED}


async def count_rows(session: AsyncSession, user_id: uuid.UUID) -> int:
    session.expire_all()
    return await session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user_id))


# --- 설정 ---


async def test_every_mutable_kind_starts_on(client: AsyncClient, my_headers: dict):
    response = await client.get(MUTES_URL, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'kinds': [{'kind': kind, 'muted': False} for kind in mutable_kinds()]}


async def test_muting_twice_is_the_same_as_once(client: AsyncClient, my_headers: dict):
    first = await client.put(f'{MUTES_URL}/credit.expiring', headers=my_headers)
    again = await client.put(f'{MUTES_URL}/credit.expiring', headers=my_headers)

    assert first.status_code == again.status_code == status.HTTP_200_OK
    assert muted_kinds(again.json()) == {'credit.expiring'}
    assert muted_kinds((await client.get(MUTES_URL, headers=my_headers)).json()) == {'credit.expiring'}


async def test_unmuting_turns_it_back_on_and_twice_is_fine(client: AsyncClient, my_headers: dict):
    await client.put(f'{MUTES_URL}/credit.expiring', headers=my_headers)
    await client.put(f'{MUTES_URL}/post.commented', headers=my_headers)

    first = await client.delete(f'{MUTES_URL}/credit.expiring', headers=my_headers)
    again = await client.delete(f'{MUTES_URL}/credit.expiring', headers=my_headers)

    assert first.status_code == again.status_code == status.HTTP_200_OK
    assert muted_kinds(again.json()) == {'post.commented'}


async def test_my_mutes_are_not_someone_elses(client: AsyncClient, my_headers: dict, other_headers: dict):
    await client.put(f'{MUTES_URL}/credit.short', headers=my_headers)

    assert muted_kinds((await client.get(MUTES_URL, headers=other_headers)).json()) == set()


@pytest.mark.parametrize('kind', ['order.paid', 'scenario.sanctioned', 'credit.welcome', 'stack.smoke'])
async def test_a_kind_that_cannot_be_muted_is_refused(
    client: AsyncClient, session: AsyncSession, my_headers: dict, kind
):
    muting = await client.put(f'{MUTES_URL}/{kind}', headers=my_headers)
    unmuting = await client.delete(f'{MUTES_URL}/{kind}', headers=my_headers)

    assert muting.status_code == unmuting.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert muting.json()['detail'] == {'code': 'kind_not_mutable', 'kind': kind}
    assert await session.scalar(select(func.count()).select_from(NotificationMute)) == 0


@pytest.mark.parametrize('method', ['GET', 'PUT', 'DELETE'])
async def test_needs_a_token(client: AsyncClient, method: str):
    url = MUTES_URL if method == 'GET' else f'{MUTES_URL}/credit.expiring'

    response = await client.request(method, url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 넣을 때 거르기 ---


async def test_a_muted_kind_is_not_written_and_the_sender_is_told_it_was_taken(
    client: AsyncClient, session: AsyncSession, my_headers: dict
):
    await client.put(f'{MUTES_URL}/post.commented', headers=my_headers)

    response = await signed_put(client, commented('comment:1'), source='board')

    # 넣는 서버는 200 을 보낸 것으로 친다. 다시 보내지 않는다
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'id': None, 'status': 'muted'}
    assert await count_rows(session, ME) == 0


async def test_muting_touches_only_that_person_and_that_kind(
    client: AsyncClient, session: AsyncSession, my_headers: dict
):
    await client.put(f'{MUTES_URL}/post.commented', headers=my_headers)

    for_other = await signed_put(client, commented('comment:1', OTHER), source='board')
    other_kind = await signed_put(
        client,
        {**commented('reply:1'), 'kind': 'comment.replied', 'payload': {**COMMENTED, 'parent_id': '10'}},
        source='board',
    )

    assert for_other.status_code == other_kind.status_code == status.HTTP_201_CREATED
    assert await count_rows(session, ME) == 1


async def test_after_unmuting_only_new_notifications_come_in(
    client: AsyncClient, session: AsyncSession, my_headers: dict
):
    await client.put(f'{MUTES_URL}/post.commented', headers=my_headers)
    await signed_put(client, commented('comment:1'), source='board')
    await client.delete(f'{MUTES_URL}/post.commented', headers=my_headers)

    response = await signed_put(client, commented('comment:2'), source='board')

    assert response.status_code == status.HTTP_201_CREATED
    assert await count_rows(session, ME) == 1


async def test_a_left_over_mute_of_a_kind_that_cannot_be_muted_is_ignored(client: AsyncClient, session: AsyncSession):
    # 표에서 끌 수 없게 바뀐 종류의 줄이 남아 있어도 결제 알림은 들어온다
    session.add(NotificationMute(user_id=ME, kind='order.paid', created_at=datetime.now(UTC)))
    await session.commit()

    response = await signed_put(
        client,
        {'source_key': 'order.paid:1', 'user_id': str(ME), 'kind': 'order.paid', 'payload': PAID},
        source='billing',
    )

    assert response.status_code == status.HTTP_201_CREATED


async def test_a_muted_notification_is_counted_as_muted(
    client: AsyncClient, my_headers: dict, metrics: MetricsRecorder
):
    await client.put(f'{MUTES_URL}/post.commented', headers=my_headers)

    await signed_put(client, commented('comment:1'), source='board')

    assert metrics.value('notifications_received', source='board', outcome='muted') == 1
