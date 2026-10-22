# trpg-server/app/chat/repository.py

"""
채팅을 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

고치는 함수와 지우는 함수가 없다.
읽는 함수는 테이블의 ID 를 받는다. 다른 테이블의 채팅이 딸려 나올 길이 없다.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import ChatMessage


def add_message(session: AsyncSession, message: ChatMessage) -> None:
    """새 채팅을 세션에 올린다."""
    session.add(message)


async def list_after(
    session: AsyncSession, table_id: uuid.UUID, after: int, limit: int, until: int | None = None
) -> list[ChatMessage]:
    """
    테이블의 채팅 중 after 번 뒤의 것을 순서대로 돌려준다. limit 개까지다. 이벤트를 읽는 방식과 같다.

    until 을 주면 그 번호까지만 준다. 기록을 내려받을 때 받기 시작한 때(떠난 사람은 떠난 때)까지만 읽는다.
    """
    query = select(ChatMessage).where(ChatMessage.table_id == table_id, ChatMessage.sequence > after)
    if until is not None:
        query = query.where(ChatMessage.sequence <= until)
    query = query.order_by(ChatMessage.sequence).limit(limit)
    return list(await session.scalars(query))


async def last_sequence(session: AsyncSession, table_id: uuid.UUID, before: datetime | None = None) -> int:
    """테이블의 마지막 채팅의 번호. before 를 주면 그 시각까지 쓴 것 중에서다. 없으면 0 이다."""
    query = select(func.coalesce(func.max(ChatMessage.sequence), 0)).where(ChatMessage.table_id == table_id)
    if before is not None:
        query = query.where(ChatMessage.created_at <= before)
    return await session.scalar(query)
