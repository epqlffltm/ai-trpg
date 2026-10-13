# game-server/app/whispers/repository.py

"""
쪽지를 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

고치는 함수와 지우는 함수가 없다.
사람이 읽는 함수는 테이블과 쪽지함의 주인을 함께 받는다. 남의 쪽지함이 딸려 나올 길이 없다.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.whispers.models import Whisper


def add_whisper(session: AsyncSession, whisper: Whisper) -> None:
    """쪽지함에 쪽지 한 장을 세션에 올린다."""
    session.add(whisper)


async def last_sequence(session: AsyncSession, table_id: uuid.UUID, owner_id: uuid.UUID) -> int:
    """이 쪽지함의 마지막 번호. 비어 있으면 0 이다."""
    query = select(func.coalesce(func.max(Whisper.sequence), 0)).where(
        Whisper.table_id == table_id, Whisper.owner_id == owner_id
    )
    return await session.scalar(query)


async def list_after(
    session: AsyncSession, table_id: uuid.UUID, owner_id: uuid.UUID, after: int, limit: int
) -> list[Whisper]:
    """이 사람의 쪽지함에서 after 번 뒤의 쪽지를 순서대로 돌려준다. limit 장까지다. 채팅을 읽는 방식과 같다."""
    query = (
        select(Whisper)
        .where(Whisper.table_id == table_id, Whisper.owner_id == owner_id, Whisper.sequence > after)
        .order_by(Whisper.sequence)
        .limit(limit)
    )
    return list(await session.scalars(query))


async def list_for_gm(session: AsyncSession, table_id: uuid.UUID, round_number: int, per_sender: int) -> list[Whisper]:
    """
    이 라운드에 GM 에게 보인 쪽지를 보낸 순서대로 돌려준다. 보낸 사람마다 최근 per_sender 장까지다.

    보낸 사람의 쪽지함에 있는 것만 읽는다. 받은 사람의 것은 같은 쪽지의 사본이다.
    보낸 사람마다 세는 것: 한 사람이 쪽지를 쏟아 내도 다른 사람의 쪽지가 밀려나지 않는다.
    """
    ranked = (
        select(
            Whisper.id,
            func.row_number().over(partition_by=Whisper.sender_id, order_by=Whisper.sequence.desc()).label('recent'),
        )
        .where(
            Whisper.table_id == table_id,
            Whisper.round_number == round_number,
            Whisper.gm_visible.is_(True),
            Whisper.owner_id == Whisper.sender_id,
        )
        .subquery()
    )
    query = (
        select(Whisper)
        .join(ranked, ranked.c.id == Whisper.id)
        .where(ranked.c.recent <= per_sender)
        .order_by(Whisper.created_at, Whisper.id)
    )
    return list(await session.scalars(query))
