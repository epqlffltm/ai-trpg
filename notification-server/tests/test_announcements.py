# notification-server/tests/test_announcements.py

"""
새 작품 알림(app/announcements/, #989)을 검증한다. 실제 DB(notification_test)에서 돈다.

  - *.published 는 user_id(만든 사람)의 팔로워마다 한 줄씩 넣는다. 열쇠는 '<작품의 열쇠>:<팔로워>' 다. 201 이다
  - 그 종류를 끈 팔로워에게는 넣지 않는다. 팔로우하지 않은 사람에게는 가지 않는다
  - 같은 열쇠가 다시 오면(다시 보냄, 다시 공개) 아무것도 넣지 않고 200 이다. 그 사이에 늘어난 팔로워에게도 가지 않는다
  - 팔로워가 없어도 기록은 남아 나중에 다시 와도 알리지 않는다(처음 한 번만)
  - 표의 규칙(넣는 서버, 꼭 있어야 하는 칸)은 다른 알림과 같다. 탈퇴하면 그 사람의 기록을 지운다
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.announcements.models import WorkAnnouncement
from app.follows.models import CreatorFollow
from app.notifications.models import Notification, NotificationMute
from app.withdrawals.service import erase_user
from tests.signing import signed_put

pytestmark = pytest.mark.usefixtures('clean_tables')

CREATOR = uuid.UUID('0b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
FAN = uuid.UUID('1b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
QUIET_FAN = uuid.UUID('2b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
LATE_FAN = uuid.UUID('3b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
STRANGER = uuid.UUID('4b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
SCENARIO = '9d1c2b3a-4e5f-4a6b-8c7d-0e1f2a3b4c5d'
KEY = f'scenario.published:{SCENARIO}'
NOW = datetime(2026, 11, 5, tzinfo=UTC)


def published(**overrides) -> dict:
    body = {
        'source_key': KEY,
        'user_id': str(CREATOR),
        'kind': 'scenario.published',
        'payload': {'scenario_id': SCENARIO, 'title': '잊힌 탑', 'creator_id': str(CREATOR)},
    }
    body.update(overrides)
    return body


async def follow(session: AsyncSession, *followers: uuid.UUID) -> None:
    for follower in followers:
        session.add(CreatorFollow(follower_id=follower, creator_id=CREATOR, created_at=NOW))
    await session.commit()


async def received(session: AsyncSession) -> list[tuple[uuid.UUID, str, str]]:
    rows = await session.execute(select(Notification.user_id, Notification.source_key, Notification.kind))
    return sorted(rows.all())


async def test_puts_one_for_each_follower_who_has_not_muted_it(client: AsyncClient, session: AsyncSession):
    await follow(session, FAN, QUIET_FAN)
    session.add(NotificationMute(user_id=QUIET_FAN, kind='scenario.published', created_at=NOW))
    await session.commit()

    response = await signed_put(client, published())

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json() == {'id': None, 'status': 'created'}
    assert await received(session) == [(FAN, f'{KEY}:{FAN}', 'scenario.published')]
    saved = await session.scalar(select(Notification))
    assert saved.payload == published()['payload']
    assert saved.source == 'game'


async def test_the_same_work_is_announced_only_once(client: AsyncClient, session: AsyncSession):
    await follow(session, FAN)
    await signed_put(client, published())
    await follow(session, LATE_FAN)

    again = await signed_put(client, published())

    assert again.status_code == status.HTTP_200_OK
    assert again.json() == {'id': None, 'status': 'existing'}
    assert [row[0] for row in await received(session)] == [FAN]


async def test_a_work_without_followers_is_still_announced_once(client: AsyncClient, session: AsyncSession):
    first = await signed_put(client, published())
    await follow(session, FAN)
    again = await signed_put(client, published())

    assert (first.status_code, again.status_code) == (status.HTTP_201_CREATED, status.HTTP_200_OK)
    assert await received(session) == []
    assert await session.scalar(select(func.count()).select_from(WorkAnnouncement)) == 1


async def test_asset_announces_characters_and_worlds(client: AsyncClient, session: AsyncSession):
    await follow(session, FAN)
    character = {'character_id': SCENARIO, 'name': '아리', 'creator_id': str(CREATOR)}
    world = {'world_id': SCENARIO, 'name': '여름', 'creator_id': str(CREATOR)}

    first = await signed_put(
        client,
        published(source_key=f'character.published:{SCENARIO}', kind='character.published', payload=character),
        source='asset',
    )
    second = await signed_put(
        client,
        published(source_key=f'world.published:{SCENARIO}', kind='world.published', payload=world),
        source='asset',
    )

    assert (first.status_code, second.status_code) == (status.HTTP_201_CREATED, status.HTTP_201_CREATED)
    assert [row[2] for row in await received(session)] == ['character.published', 'world.published']


async def test_follows_the_catalog_rules(client: AsyncClient, session: AsyncSession):
    await follow(session, FAN)

    wrong_server = await signed_put(client, published(), source='asset')
    missing = await signed_put(client, published(payload={'scenario_id': SCENARIO, 'title': '잊힌 탑'}))

    assert wrong_server.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert wrong_server.json()['detail']['code'] == 'kind_not_allowed'
    assert missing.json()['detail'] == {
        'code': 'payload_missing_fields',
        'kind': 'scenario.published',
        'missing': ['creator_id'],
    }
    assert await session.scalar(select(func.count()).select_from(WorkAnnouncement)) == 0


async def test_withdrawal_erases_the_creators_announcements(client: AsyncClient, session: AsyncSession):
    await signed_put(client, published())
    await signed_put(client, published(source_key='scenario.published:other', user_id=str(STRANGER)))

    erased = await erase_user(session, CREATOR)

    assert erased.announcements == 1
    left = await session.scalars(select(WorkAnnouncement.creator_id))
    assert list(left) == [STRANGER]
