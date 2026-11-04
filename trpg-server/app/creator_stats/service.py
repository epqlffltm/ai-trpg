# trpg-server/app/creator_stats/service.py

"""제작자 숫자를 모은다(#991). 읽은 줄을 더하고 자른다. DB 는 repository 가 읽는다."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.creator_stats import repository
from app.creator_stats.schemas import ScenarioStats, WorkStarts

# "최근"의 날 수. 랭킹(app/rankings/)과 asset 서버의 것과 같다
RECENT_DAYS = 7
# 응답에 싣는 작품의 수. 더한 수는 모두를 센다
MAX_STATS_ITEMS = 100


async def scenario_stats(session: AsyncSession, owner_id: uuid.UUID, now: datetime | None = None) -> ScenarioStats:
    """내 시나리오의 숫자."""
    since = (now or datetime.now(UTC)) - timedelta(days=RECENT_DAYS)
    rows = await repository.owned_scenario_starts(session, owner_id, since)
    return summarize(rows)


def summarize(rows: list[tuple[uuid.UUID, str, int, int]]) -> ScenarioStats:
    """줄을 더하고 앞의 MAX_STATS_ITEMS 개만 싣는다."""
    return ScenarioStats(
        recent_days=RECENT_DAYS,
        total=sum(row[2] for row in rows),
        recent=sum(row[3] for row in rows),
        items=[
            WorkStarts(id=work_id, title=title, total=total, recent=recent)
            for work_id, title, total, recent in rows[:MAX_STATS_ITEMS]
        ],
    )
