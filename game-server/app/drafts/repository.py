# game-server/app/drafts/repository.py

"""
장부 초안의 줄을 DB 에서 읽고 쓴다. 규칙을 모른다. 저장(commit)은 부르는 쪽이 한다.
"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.drafts.models import DraftStatus, LedgerDraft


async def expire_pending(session: AsyncSession, table_id: uuid.UUID) -> int:
    """이 테이블에서 방장의 결정을 기다리던 줄을 모두 만료시킨다. 만료시킨 줄의 수를 돌려준다."""
    query = (
        update(LedgerDraft)
        .where(LedgerDraft.table_id == table_id, LedgerDraft.status == DraftStatus.PENDING)
        .values(status=DraftStatus.EXPIRED, decided_at=func.now())
    )
    result = await session.execute(query)
    return result.rowcount


def add_drafts(session: AsyncSession, rows: list[LedgerDraft]) -> None:
    """새 줄들을 세션에 더한다."""
    session.add_all(rows)


async def list_pending(session: AsyncSession, table_id: uuid.UUID) -> list[LedgerDraft]:
    """이 테이블에서 방장의 결정을 기다리는 줄들. 라운드와 쓴 순서다."""
    query = (
        select(LedgerDraft)
        .where(LedgerDraft.table_id == table_id, LedgerDraft.status == DraftStatus.PENDING)
        .order_by(LedgerDraft.round_number, LedgerDraft.position)
    )
    return list(await session.scalars(query))


async def find_draft(session: AsyncSession, table_id: uuid.UUID, draft_id: uuid.UUID) -> LedgerDraft | None:
    """이 테이블의 그 줄. 없거나 다른 테이블의 줄이면 None."""
    query = select(LedgerDraft).where(LedgerDraft.id == draft_id, LedgerDraft.table_id == table_id)
    return await session.scalar(query)
