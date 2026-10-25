# notification-server/tests/test_inbox.py

"""
사용자가 자기 알림함을 읽는 API(/api/v1/notification/me/notifications)를 검증한다.

  - 내 알림만 보인다. 남의 알림 번호를 대면 없는 것과 같다(404)
  - 최근 것부터 읽고, 쪽은 번호(before)로 넘긴다
  - 읽음은 처음 읽은 시각이다. 모두 읽음은 화면이 받은 번호(up_to)까지만이다
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inbox import repository
from app.inbox.schemas import PAGE_SIZE_MAX
from app.main import API_PREFIX
from app.notifications.models import Notification

pytestmark = pytest.mark.usefixtures('clean_tables')

INBOX_URL = f'{API_PREFIX}/me/notifications'
ME = uuid.UUID('0b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
OTHER = uuid.UUID('b1c2d3e4-f5a6-4b7c-8d9e-0f1a2b3c4d5e')
CREATED_AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


@pytest.fixture
def my_headers(signing_key: SigningKey) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(ME)))}'}


@pytest.fixture
def other_headers(signing_key: SigningKey) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(OTHER)))}'}


async def add_notifications(session: AsyncSession, user_id: uuid.UUID, count: int, **fields) -> list[int]:
    """이 사람에게 알림을 count 개 넣는다. 넣은 차례대로 번호를 돌려준다."""
    rows = [
        Notification(
            user_id=user_id,
            source='game',
            source_key=f'{user_id}:{uuid.uuid4()}',
            kind='scenario.sanctioned',
            payload={'number': index},
            created_at=CREATED_AT + timedelta(minutes=index),
            **fields,
        )
        for index in range(count)
    ]
    session.add_all(rows)
    await session.commit()
    return [row.id for row in rows]


async def read_page(client: AsyncClient, headers: dict, **params) -> dict:
    return (await client.get(INBOX_URL, params=params, headers=headers)).json()


async def read_at_of(session: AsyncSession, notification_id: int) -> datetime | None:
    session.expire_all()
    return await session.scalar(select(Notification.read_at).where(Notification.id == notification_id))


# --- 목록 ---


async def test_an_empty_inbox(client: AsyncClient, my_headers: dict):
    response = await client.get(INBOX_URL, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'items': [], 'next_before': None}


async def test_lists_only_my_notifications_newest_first(client: AsyncClient, session: AsyncSession, my_headers: dict):
    mine = await add_notifications(session, ME, 3)
    await add_notifications(session, OTHER, 2)

    response = await client.get(INBOX_URL, headers=my_headers)

    items = response.json()['items']
    assert [item['id'] for item in items] == list(reversed(mine))
    assert items[0] == {
        'id': mine[-1],
        'source': 'game',
        'kind': 'scenario.sanctioned',
        'payload': {'number': 2},
        'created_at': '2026-10-18T09:02:00Z',
        'read_at': None,
    }


async def test_pages_follow_next_before(client: AsyncClient, session: AsyncSession, my_headers: dict):
    mine = await add_notifications(session, ME, 5)

    first = await read_page(client, my_headers, limit=2)
    second = await read_page(client, my_headers, limit=2, before=first['next_before'])
    third = await read_page(client, my_headers, limit=2, before=second['next_before'])

    pages = [[item['id'] for item in page['items']] for page in (first, second, third)]
    assert pages == [[mine[4], mine[3]], [mine[2], mine[1]], [mine[0]]]
    assert third['next_before'] is None


async def test_a_page_that_ends_exactly_has_no_next(client: AsyncClient, session: AsyncSession, my_headers: dict):
    # 꼭 limit 개가 남았을 때 빈 쪽을 한 번 더 부르게 하지 않는다
    await add_notifications(session, ME, 2)

    response = await client.get(INBOX_URL, params={'limit': 2}, headers=my_headers)

    assert len(response.json()['items']) == 2
    assert response.json()['next_before'] is None


@pytest.mark.parametrize('params', [{'limit': 0}, {'limit': PAGE_SIZE_MAX + 1}, {'before': 0}, {'before': 'x'}])
async def test_refuses_a_page_of_the_wrong_shape(client: AsyncClient, my_headers: dict, params: dict):
    response = await client.get(INBOX_URL, params=params, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    # 칸이 틀린 요청은 서버들이 함께 쓰는 본문이다(server_core/input_errors.py)
    assert list(response.json()['errors']) == list(params)


async def test_cannot_pick_whose_inbox_to_read(client: AsyncClient, session: AsyncSession, my_headers: dict):
    # 누구의 알림함인지는 토큰에서만 정한다. 쿼리로 남의 번호를 붙여도 내 것이다
    await add_notifications(session, OTHER, 1)

    response = await client.get(INBOX_URL, params={'user_id': str(OTHER)}, headers=my_headers)

    assert response.json()['items'] == []


# --- 읽지 않은 수 ---


async def test_counts_only_my_unread(client: AsyncClient, session: AsyncSession, my_headers: dict):
    await add_notifications(session, ME, 3)
    await add_notifications(session, ME, 2, read_at=CREATED_AT + timedelta(hours=1))
    await add_notifications(session, OTHER, 4)

    response = await client.get(f'{INBOX_URL}/unread-count', headers=my_headers)

    assert response.json() == {'unread': 3}


# --- 하나 읽음 ---


async def test_reads_one(client: AsyncClient, session: AsyncSession, my_headers: dict):
    (notification_id,) = await add_notifications(session, ME, 1)

    response = await client.post(f'{INBOX_URL}/{notification_id}/read', headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['id'] == notification_id
    assert response.json()['read_at'] is not None
    assert (await client.get(f'{INBOX_URL}/unread-count', headers=my_headers)).json() == {'unread': 0}


async def test_reading_again_keeps_the_first_time(client: AsyncClient, session: AsyncSession, my_headers: dict):
    (notification_id,) = await add_notifications(session, ME, 1)
    first = await client.post(f'{INBOX_URL}/{notification_id}/read', headers=my_headers)

    again = await client.post(f'{INBOX_URL}/{notification_id}/read', headers=my_headers)

    assert again.status_code == status.HTTP_200_OK
    assert again.json()['read_at'] == first.json()['read_at']


async def test_cannot_read_someone_elses(
    client: AsyncClient, session: AsyncSession, my_headers: dict, other_headers: dict
):
    (theirs,) = await add_notifications(session, OTHER, 1)

    response = await client.post(f'{INBOX_URL}/{theirs}/read', headers=my_headers)

    # 없는 알림과 같은 답이다. 남의 알림이 있는지 알리지 않는다
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == (await client.post(f'{INBOX_URL}/999999999/read', headers=my_headers)).json()
    assert await read_at_of(session, theirs) is None


async def test_a_notification_removed_while_reading_is_not_found(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient, session: AsyncSession, my_headers: dict
):
    # 읽음을 적은 뒤 다시 읽기 전에 보관 기간의 정리가 지웠다
    (notification_id,) = await add_notifications(session, ME, 1)

    async def gone(*args) -> None:
        return None

    monkeypatch.setattr(repository, 'find_own', gone)

    response = await client.post(f'{INBOX_URL}/{notification_id}/read', headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- 모두 읽음 ---


async def test_reads_all_up_to_the_number_the_screen_saw(client: AsyncClient, session: AsyncSession, my_headers: dict):
    mine = await add_notifications(session, ME, 4)
    # 화면이 목록을 받은 뒤에 들어온 알림이다. 보이지 않았으니 읽음이 되지 않는다
    (arrived_later,) = await add_notifications(session, ME, 1)
    (theirs,) = await add_notifications(session, OTHER, 1)

    response = await client.post(f'{INBOX_URL}/read-all', json={'up_to': mine[-1]}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'read': 4}
    assert await read_at_of(session, arrived_later) is None
    assert await read_at_of(session, theirs) is None
    assert (await client.get(f'{INBOX_URL}/unread-count', headers=my_headers)).json() == {'unread': 1}


async def test_reading_all_again_reads_nothing_more(client: AsyncClient, session: AsyncSession, my_headers: dict):
    mine = await add_notifications(session, ME, 2)
    await client.post(f'{INBOX_URL}/read-all', json={'up_to': mine[-1]}, headers=my_headers)

    response = await client.post(f'{INBOX_URL}/read-all', json={'up_to': mine[-1]}, headers=my_headers)

    assert response.json() == {'read': 0}


@pytest.mark.parametrize('body', [{}, {'up_to': 0}, {'up_to': 'all'}, {'up_to': 5, 'user_id': str(OTHER)}])
async def test_refuses_read_all_of_the_wrong_shape(client: AsyncClient, my_headers: dict, body: dict):
    response = await client.post(f'{INBOX_URL}/read-all', json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 토큰 ---


@pytest.mark.parametrize(
    ('method', 'path'),
    [
        ('GET', ''),
        ('GET', '/unread-count'),
        ('POST', '/1/read'),
        ('POST', '/read-all'),
    ],
)
async def test_every_address_needs_a_token(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{INBOX_URL}{path}', json={'up_to': 1})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
