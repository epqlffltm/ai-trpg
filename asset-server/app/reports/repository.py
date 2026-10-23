# asset-server/app/reports/repository.py

"""
신고를 DB 에서 읽고 쓴다. 커밋하지 않는다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character
from app.reports.models import CharacterReport, ReportReason


@dataclass(frozen=True)
class OpenGroup:
    """열린 신고를 캐릭터마다 묶은 것. reasons 는 사유마다의 수다."""

    character_id: uuid.UUID
    name: str
    hidden: bool
    open_count: int
    reasons: dict[str, int]
    first_reported_at: datetime
    last_reported_at: datetime


def add(session: AsyncSession, report: CharacterReport) -> None:
    """새 신고를 세션에 올린다."""
    session.add(report)


def reason_count(reason: ReportReason):
    """그 사유의 열린 신고의 수를 세는 식."""
    return func.count().filter(CharacterReport.reason == reason).label(reason.value)


async def open_groups(session: AsyncSession, limit: int, offset: int) -> tuple[list[OpenGroup], int]:
    """
    열린 신고를 캐릭터마다 묶은 한 쪽과 전체 묶음의 수.
    minor 가 있는 것이 먼저, 그다음 마지막 신고가 최근인 것부터다.
    """
    counts = [reason_count(reason) for reason in ReportReason]
    minor = func.count().filter(CharacterReport.reason == ReportReason.MINOR)
    query = (
        select(
            CharacterReport.character_id,
            Character.name,
            Character.hidden_at,
            func.count().label('open_count'),
            func.min(CharacterReport.created_at).label('first_reported_at'),
            func.max(CharacterReport.created_at).label('last_reported_at'),
            *counts,
        )
        .join(Character, Character.id == CharacterReport.character_id)
        .where(CharacterReport.handled_at.is_(None))
        .group_by(CharacterReport.character_id, Character.name, Character.hidden_at)
        .order_by((minor > 0).desc(), func.max(CharacterReport.created_at).desc(), CharacterReport.character_id)
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(
        select(func.count(func.distinct(CharacterReport.character_id))).where(CharacterReport.handled_at.is_(None))
    )
    groups = [
        OpenGroup(
            character_id=row.character_id,
            name=row.name,
            hidden=row.hidden_at is not None,
            open_count=row.open_count,
            reasons={reason.value: getattr(row, reason.value) for reason in ReportReason},
            first_reported_at=row.first_reported_at,
            last_reported_at=row.last_reported_at,
        )
        for row in await session.execute(query)
    ]
    return groups, total or 0


async def list_for_character(session: AsyncSession, character_id: uuid.UUID) -> list[CharacterReport]:
    """그 캐릭터의 신고 전부(처리된 것까지). 최근 것부터다."""
    query = (
        select(CharacterReport)
        .where(CharacterReport.character_id == character_id)
        .order_by(CharacterReport.created_at.desc(), CharacterReport.id)
    )
    return list(await session.scalars(query))


async def handle_open(
    session: AsyncSession, character_id: uuid.UUID, operator_id: uuid.UUID, outcome: str, now: datetime
) -> int:
    """그 캐릭터의 열린 신고를 모두 처리한 것으로 적는다. 적은 수를 돌려준다."""
    statement = (
        update(CharacterReport)
        .where(CharacterReport.character_id == character_id, CharacterReport.handled_at.is_(None))
        .values(handled_at=now, handled_by=operator_id, outcome=outcome)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(statement)
    return result.rowcount
