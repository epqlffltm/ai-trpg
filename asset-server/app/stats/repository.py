# asset-server/app/stats/repository.py

"""
작품마다의 시작 수를 DB 에 쓴다(#985). SQL 은 이 파일에만 있다. 커밋하지 않는다.

받은 수(work_starts)를 바꿔 넣고, 카드에 보일 모든 수를 작품의 행(start_count)에도 옮겨 적는다.
목록마다 잇지 않으려고 적어 둔다. 바뀐 행만 고치고, 고친 시각(updated_at)은 건드리지 않는다(사람이 고친 것이 아니다).
"""

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character
from app.stats.client import ReceivedStartsList
from app.stats.models import WorkKind, WorkStarts
from app.worlds.models import World

# 종류마다 수를 옮겨 적을 작품의 표
WORKS = {WorkKind.CHARACTER: Character, WorkKind.WORLD: World}


async def replace_starts(session: AsyncSession, kind: WorkKind, received: ReceivedStartsList, now: datetime) -> None:
    """그 종류의 줄을 받은 것으로 통째로 바꾼다. 받은 것에 없는 작품은 지워진다."""
    await session.execute(delete(WorkStarts).where(WorkStarts.kind == kind))
    rows = [
        {
            'kind': kind,
            'work_id': item.work_id,
            'total': item.total,
            'recent': item.recent,
            'recent_days': received.recent_days,
            'refreshed_at': now,
        }
        for item in received.items
    ]
    if rows:
        await session.execute(insert(WorkStarts), rows)
    await copy_totals(session, kind)


async def copy_totals(session: AsyncSession, kind: WorkKind) -> None:
    """그 종류의 모든 수를 작품의 행에 옮겨 적는다. 받은 수가 없는 작품은 0 이다. 값이 바뀐 행만 고친다."""
    work = WORKS[kind]
    total = select(WorkStarts.total).where(WorkStarts.kind == kind, WorkStarts.work_id == work.id).scalar_subquery()
    received = func.coalesce(total, 0)
    await session.execute(
        update(work)
        .where(work.start_count != received)
        .values(start_count=received, updated_at=work.updated_at)
        .execution_options(synchronize_session=False)
    )
