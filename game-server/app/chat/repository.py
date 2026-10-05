# game-server/app/chat/repository.py

"""
채팅을 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

고치는 함수와 지우는 함수가 없다.
읽는 함수는 테이블의 ID 를 받는다. 다른 테이블의 채팅이 딸려 나올 길이 없다.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import ChatMessage


def add_message(session: AsyncSession, message: ChatMessage) -> None:
    """새 채팅을 세션에 올린다."""
    session.add(message)


async def list_after(session: AsyncSession, table_id: uuid.UUID, after: int, limit: int) -> list[ChatMessage]:
    """테이블의 채팅 중 after 번 뒤의 것을 순서대로 돌려준다. limit 개까지다. 이벤트를 읽는 방식과 같다."""
    query = (
        select(ChatMessage)
        .where(ChatMessage.table_id == table_id, ChatMessage.sequence > after)
        .order_by(ChatMessage.sequence)
        .limit(limit)
    )
    return list(await session.scalars(query))
