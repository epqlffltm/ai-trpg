# asset-server/app/creator_stats/service.py

"""제작자 숫자를 모은다(#991). 읽은 줄을 더하고 자른다. DB 는 repository 가 읽는다."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.creator_stats import repository
from app.creator_stats.schemas import WorkStarts, WorkStats
from app.rankings.repository import refreshed_at
from app.stats.models import WorkKind

# "최근"의 날 수. 랭킹(app/rankings/)과 chat·story 서버의 app/stats 와 같다
RECENT_DAYS = 7
# 응답에 싣는 작품의 수. 더한 수는 모두를 센다
MAX_STATS_ITEMS = 100


async def work_stats(session: AsyncSession, kind: WorkKind, owner_id: uuid.UUID) -> WorkStats:
    """내 캐릭터(또는 세계관)의 숫자."""
    rows = await repository.owned_work_starts(session, kind, owner_id)
    return summarize(rows, await refreshed_at(session, kind))


def summarize(rows: list[tuple[uuid.UUID, str, int, int]], received_at: datetime | None) -> WorkStats:
    """줄을 더하고 앞의 MAX_STATS_ITEMS 개만 싣는다."""
    return WorkStats(
        recent_days=RECENT_DAYS,
        refreshed_at=received_at,
        total=sum(row[2] for row in rows),
        recent=sum(row[3] for row in rows),
        items=[
            WorkStarts(id=work_id, title=title, total=total, recent=recent)
            for work_id, title, total, recent in rows[:MAX_STATS_ITEMS]
        ],
    )
