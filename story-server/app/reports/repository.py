# story-server/app/reports/repository.py

"""
세션 속 답의 신고를 DB 에서 읽고 쓴다. 커밋하지 않는다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.reports.models import MessageReport, ReportReason


@dataclass(frozen=True)
class HandledReport:
    """처리한 신고 하나와 신고한 사람, 신고한 때의 세계관 이름. 처리했다는 알림을 보낼 때 쓴다."""

    report_id: uuid.UUID
    reporter_id: uuid.UUID
    world_name: str


def add(session: AsyncSession, report: MessageReport) -> None:
    """새 신고를 세션에 올린다."""
    session.add(report)


async def list_open(session: AsyncSession, limit: int, offset: int) -> tuple[list[MessageReport], int]:
    """열린 신고의 한 쪽과 전체 수. minor 가 먼저, 그다음 오래된 것부터(먼저 온 것을 먼저 본다)."""
    condition = MessageReport.handled_at.is_(None)
    minor_first = case((MessageReport.reason == ReportReason.MINOR, 0), else_=1)
    query = (
        select(MessageReport)
        .where(condition)
        .order_by(minor_first, MessageReport.created_at, MessageReport.id)
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(select(func.count()).select_from(MessageReport).where(condition))
    return list(await session.scalars(query)), total or 0


async def get(session: AsyncSession, report_id: uuid.UUID) -> MessageReport | None:
    """신고 하나. 없으면 None."""
    return await session.get(MessageReport, report_id)


async def handle(
    session: AsyncSession, report_id: uuid.UUID, operator_id: uuid.UUID, outcome: str, now: datetime
) -> HandledReport | None:
    """
    열린 신고를 처리한 것으로 적는다. 이미 처리했거나 없으면 바꾸지 않고 None. 확인과 적기를 한 문장으로 한다.

    처리한 신고의 신고한 사람과 세계관의 이름을 돌려준다(처리 알림이 쓴다).
    """
    statement = (
        update(MessageReport)
        .where(MessageReport.id == report_id, MessageReport.handled_at.is_(None))
        .values(handled_at=now, handled_by=operator_id, outcome=outcome)
        .returning(MessageReport.id, MessageReport.reporter_id, MessageReport.world_name)
        .execution_options(synchronize_session=False)
    )
    row = (await session.execute(statement)).first()
    return None if row is None else HandledReport(*row)
