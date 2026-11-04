# trpg-server/app/rankings/repository.py

"""
시나리오의 랭킹을 DB 에서 읽는다(#985). SQL 은 이 파일에만 있다.

연 테이블(game_tables)을 시나리오마다 센다. 판이 여럿이어도 시나리오 하나로 합친다. 끝난 테이블도 센다(한 번 연 일이다).
공개 목록의 조건(visible, listed, filtered)에 맞는 것만이다. 최근의 수가 0 인 것은 빠진다.
같으면 모든 수, 그것도 같으면 최근에 공개한 것이 먼저다.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.assets.models import Rating, ScenarioVersion
from app.listings.models import Listing
from app.listings.repository import ListingFilter, PublicRow, filtered, listed, visible
from app.tables.models import GameTable


async def ranked_scenarios(
    session: AsyncSession, allowed_ratings: list[Rating], where: ListingFilter, recent_since: datetime, limit: int
) -> list[tuple[PublicRow, int]]:
    """볼 수 있는 시나리오의 랭킹. 공개 정보와 recent_since 뒤에 연 테이블의 수다."""
    recent = func.count().filter(GameTable.created_at >= recent_since)
    counts = (
        select(GameTable.scenario_id, recent.label('recent'), func.count().label('total'))
        .group_by(GameTable.scenario_id)
        .subquery()
    )
    query = (
        listed(filtered(visible(allowed_ratings), where))
        .add_columns(counts.c.recent)
        .join(counts, counts.c.scenario_id == Listing.scenario_id)
        .where(counts.c.recent > 0)
        .options(defer(ScenarioVersion.snapshot))
        .order_by(counts.c.recent.desc(), counts.c.total.desc(), Listing.published_at.desc(), Listing.scenario_id)
        .limit(limit)
    )
    rows = await session.execute(query)
    return [((listing, asset, version), starts) for listing, asset, version, starts in rows.all()]
