# asset-server/app/creator_stats/repository.py

"""
제작자의 작품마다 받아 둔 시작 수를 DB 에서 읽는다(#991). SQL 은 이 파일에만 있다.

랭킹과 같은 표(work_starts)를 읽는다. 실행 중에 chat 과 story 서버를 부르지 않는다.
내 작품 가운데 게시한 적이 있거나 받은 수가 있는 것만이다(게시하지 않은 초안은 빠진다).
"""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.stats.models import WorkKind, WorkStarts
from app.stats.repository import WORKS


async def owned_work_starts(
    session: AsyncSession, kind: WorkKind, owner_id: uuid.UUID
) -> list[tuple[uuid.UUID, str, int, int]]:
    """내 작품마다 (id, 이름, 모든 수, 최근의 수). 최근의 수가 많은 것부터, 같으면 모든 수, 이름의 차례다."""
    work: Any = WORKS[kind]
    total = func.coalesce(WorkStarts.total, 0)
    recent = func.coalesce(WorkStarts.recent, 0)
    query = (
        select(work.id, work.name, total, recent)
        .outerjoin(WorkStarts, (WorkStarts.kind == kind) & (WorkStarts.work_id == work.id))
        .where(work.owner_id == owner_id, or_(work.latest_version.is_not(None), WorkStarts.work_id.is_not(None)))
        .order_by(recent.desc(), total.desc(), work.name, work.id)
    )
    return [(row[0], row[1], row[2], row[3]) for row in (await session.execute(query)).all()]
