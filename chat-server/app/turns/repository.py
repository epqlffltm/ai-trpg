# chat-server/app/turns/repository.py

"""
말 한 번에 쓰는 SQL. 대화의 차례 잡기와 놓기, 말 붙이기, 호출과 청구의 기록. 커밋하지 않는다.

차례(generating_since)는 조건을 붙인 UPDATE 하나로 잡는다. 비어 있거나 오래된 것만 잡는다.
두 요청이 함께 와도 하나만 한 줄을 바꾼다(Postgres 가 그 줄을 잠그고 차례로 본다).
잠금(SELECT ... FOR UPDATE)을 따로 쥐지 않는다.
차례를 잡는 같은 트랜잭션에서 사람의 말이 붙으므로 대화의 수정 시각(updated_at)이 그때 바뀐다.
목록은 최근에 말한 것부터다.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message
from app.turns.models import DUE_STATUSES, OPEN_STATUSES, BillingStatus, Generation


async def lock_turn(session: AsyncSession, conversation_id: uuid.UUID, now: datetime, stale: timedelta) -> bool:
    """대화의 차례를 잡는다. 아무도 쥐고 있지 않거나 쥔 지 stale 이 지났으면 잡고 True, 아니면 False."""
    statement = (
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            or_(Conversation.generating_since.is_(None), Conversation.generating_since < now - stale),
        )
        .values(generating_since=now)
        .returning(Conversation.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).first() is not None


async def unlock_turn(session: AsyncSession, conversation_id: uuid.UUID) -> None:
    """대화의 차례를 놓는다. 답이 없었다(사람의 말만 붙었다)."""
    statement = (
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(generating_since=None)
        .execution_options(synchronize_session=False)
    )
    await session.execute(statement)


async def finish_turn(session: AsyncSession, conversation_id: uuid.UUID, leaf_id: uuid.UUID) -> None:
    """답을 붙이고 차례를 놓는다. 지금 가지의 끝이 그 답이 되고, 수정 시각이 지금이 된다(목록의 맨 앞)."""
    statement = (
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(generating_since=None, active_leaf_id=leaf_id)
        .execution_options(synchronize_session=False)
    )
    await session.execute(statement)


async def move_leaf(session: AsyncSession, conversation_id: uuid.UUID, leaf_id: uuid.UUID) -> None:
    """지금 가지의 끝을 옮긴다(사람의 말을 붙였다). 차례는 그대로 쥐고 있다. 수정 시각이 지금이 된다."""
    statement = (
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(active_leaf_id=leaf_id)
        .execution_options(synchronize_session=False)
    )
    await session.execute(statement)


def add(session: AsyncSession, row: Message | Generation) -> None:
    """새 행을 세션에 올린다."""
    session.add(row)


async def get_generation(session: AsyncSession, generation_id: uuid.UUID) -> Generation | None:
    """기록 하나. 없으면 None."""
    return await session.get(Generation, generation_id, populate_existing=True)


async def move_billing(
    session: AsyncSession, generation_id: uuid.UUID, expected: frozenset[BillingStatus], values: dict[str, object]
) -> bool:
    """
    청구의 상태가 expected 중 하나일 때만 values 로 고친다. 고쳤으면 True.

    정리 작업과 말 한 번이 같은 청구를 함께 만져도 한쪽만 옮긴다. 상태는 한 방향으로만 간다(app/turns/models.py).
    """
    statement = (
        update(Generation)
        .where(Generation.id == generation_id, Generation.billing_status.in_([status.value for status in expected]))
        .values(**values)
        .returning(Generation.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).first() is not None


async def find_due(session: AsyncSession, now: datetime, stale: timedelta, limit: int) -> list[Generation]:
    """
    결제 서버에 맡길 차례가 된 청구들. 확정할 것과 돌려줄 것 가운데 맡길 때가 된 것, 그리고 도중에 오래 남은 것.

    오래 남은 것(pending, held 인 채로 stale 이 지났다)은 서버가 말 한 번의 도중에 꺼진 것이다. 부르는 쪽이 돌려준다.
    """
    due = Generation.billing_status.in_([status.value for status in DUE_STATUSES]) & or_(
        Generation.next_settle_at.is_(None), Generation.next_settle_at <= now
    )
    abandoned = Generation.billing_status.in_([status.value for status in OPEN_STATUSES]) & (
        Generation.created_at < now - stale
    )
    query = select(Generation).where(or_(due, abandoned)).order_by(Generation.created_at).limit(limit)
    return list(await session.scalars(query))
