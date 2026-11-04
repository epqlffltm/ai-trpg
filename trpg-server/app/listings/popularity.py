# trpg-server/app/listings/popularity.py

"""
시나리오가 얼마나 쓰였는가(#985). 연 테이블(game_tables)을 센다. SQL 은 이 파일에만 있다.

  - 카드의 수(start_count)는 모든 기간의 수다. 끝난 테이블도 센다(한 번 연 일이다)
  - 인기순은 최근 POPULAR_DAYS 일에 연 수가 많은 것부터, 같으면 모든 수, 그것도 같으면 최근에 공개한 것이다(랭킹과 같다)
테이블이 이 서버에 있어 읽을 때 바로 센다. chat 과 story 의 수는 asset 서버가 한 시간마다 받아 온다.
"""

import enum
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.listings.models import Listing
from app.tables.models import GameTable

# 인기순의 "최근". 랭킹(app/rankings/)과 같다
POPULAR_DAYS = 7


class ListingOrder(enum.StrEnum):
    """공개 목록의 차례. recent 는 최근에 공개한 것부터, popular 는 최근 7일에 많이 연 것부터다."""

    RECENT = 'recent'
    POPULAR = 'popular'


def popular_since(now: datetime | None = None) -> datetime:
    """인기순이 세는 시작 시각."""
    return (now or datetime.now(UTC)) - timedelta(days=POPULAR_DAYS)


def by_popularity(query: Select, since: datetime) -> Select:
    """목록을 인기순으로 줄 세운다. 연 적이 없는 것은 0 으로 보고 뒤에 둔다."""
    counts = (
        select(
            GameTable.scenario_id,
            func.count().filter(GameTable.created_at >= since).label('recent'),
            func.count().label('total'),
        )
        .group_by(GameTable.scenario_id)
        .subquery()
    )
    return query.outerjoin(counts, counts.c.scenario_id == Listing.scenario_id).order_by(
        func.coalesce(counts.c.recent, 0).desc(),
        func.coalesce(counts.c.total, 0).desc(),
        Listing.published_at.desc(),
        Listing.scenario_id,
    )


async def start_counts(session: AsyncSession, scenario_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    """시나리오마다 연 테이블의 모든 수. 연 적이 없으면 빠진다(0 으로 본다). 한 번의 쿼리다."""
    if not scenario_ids:
        return {}
    query = (
        select(GameTable.scenario_id, func.count())
        .where(GameTable.scenario_id.in_(scenario_ids))
        .group_by(GameTable.scenario_id)
    )
    return {scenario_id: count for scenario_id, count in (await session.execute(query)).all()}
