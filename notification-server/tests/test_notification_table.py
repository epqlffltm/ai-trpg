# notification-server/tests/test_notification_table.py

"""
알림함 테이블(notifications)의 제약을 DB 에서 검증한다.

API 가 검사하더라도 DB 가 마지막으로 막는다. 코드에 실수가 있어도 틀린 줄이 쌓이지 않는다.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import PAYLOAD_MAX_BYTES, Notification

pytestmark = pytest.mark.usefixtures('clean_tables')

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
USER = uuid.UUID('0b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')


def make_notification(**overrides) -> Notification:
    """알림 한 줄. 테스트가 바꿀 값만 넘긴다."""
    fields = {
        'user_id': USER,
        'source': 'game',
        'source_key': 'scenario-sanction:1',
        'kind': 'scenario.sanctioned',
        'payload': {'scenario_id': '9d1c2b3a-4e5f-4a6b-8c7d-0e1f2a3b4c5d'},
        'created_at': NOW,
    }
    fields.update(overrides)
    return Notification(**fields)


async def save(session: AsyncSession, *notifications: Notification) -> None:
    session.add_all(notifications)
    await session.commit()


async def test_saves_a_notification_with_a_rising_number(session: AsyncSession):
    first, second = make_notification(), make_notification(source_key='scenario-sanction:2')

    await save(session, first, second)

    assert second.id > first.id
    assert first.read_at is None


async def test_the_same_key_from_the_same_server_is_one_row(session: AsyncSession):
    await save(session, make_notification())

    with pytest.raises(IntegrityError, match='uq_notifications_source_key'):
        await save(session, make_notification(payload={'again': True}))


async def test_the_same_key_from_another_server_is_another_row(session: AsyncSession):
    # 열쇠는 넣는 서버 안에서만 겹치지 않으면 된다
    await save(session, make_notification(), make_notification(source='billing'))

    assert await session.scalar(select(func.count()).select_from(Notification)) == 2


@pytest.mark.parametrize(
    ('field', 'value', 'constraint'),
    [
        ('source', 'Game', 'source_format'),
        ('source', '1game', 'source_format'),
        ('kind', 'Scenario.Sanctioned', 'kind_format'),
        ('kind', 'scenario..sanctioned', 'kind_format'),
        ('kind', 'scenario.', 'kind_format'),
        ('payload', ['not', 'an', 'object'], 'payload_is_object'),
        ('payload', {'text': 'x' * PAYLOAD_MAX_BYTES}, 'payload_size'),
        ('read_at', NOW - timedelta(seconds=1), 'read_after_created'),
    ],
)
async def test_refuses_a_row_of_the_wrong_shape(session: AsyncSession, field: str, value: object, constraint: str):
    with pytest.raises(IntegrityError, match=f'ck_notifications_{constraint}'):
        await save(session, make_notification(**{field: value}))


async def test_a_notification_can_be_read_at_the_time_it_came(session: AsyncSession):
    notification = make_notification(read_at=NOW)

    await save(session, notification)

    assert notification.read_at == NOW
