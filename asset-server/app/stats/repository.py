# asset-server/app/stats/repository.py

"""작품마다의 시작 수를 DB 에 쓴다(#985). SQL 은 이 파일에만 있다. 커밋하지 않는다."""

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.stats.client import ReceivedStartsList
from app.stats.models import WorkKind, WorkStarts


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
