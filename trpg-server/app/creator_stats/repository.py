# trpg-server/app/creator_stats/repository.py

"""
제작자의 시나리오마다 연 테이블의 수를 DB 에서 읽는다(#991). SQL 은 이 파일에만 있다.

랭킹(app/rankings/)과 같은 표(game_tables)를 센다. 끝난 테이블도 센다.
내 시나리오 가운데 지금 공개 중이거나 한 번이라도 테이블이 열린 것만이다(초안만 있는 것은 빠진다).
"""

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetType
from app.listings.models import Listing
from app.tables.models import GameTable


async def owned_scenario_starts(
    session: AsyncSession, owner_id: uuid.UUID, recent_since: datetime
) -> list[tuple[uuid.UUID, str, int, int]]:
    """내 시나리오마다 (id, 제목, 모든 수, 최근의 수). 최근의 수가 많은 것부터, 같으면 모든 수, 제목의 차례다."""
    total = func.count(GameTable.id)
    recent = func.count(GameTable.id).filter(GameTable.created_at >= recent_since)
    published = func.bool_or(Listing.version_id.is_not(None))
    query = (
        select(Asset.id, Asset.title, total, recent)
        .outerjoin(GameTable, GameTable.scenario_id == Asset.id)
        .outerjoin(Listing, Listing.scenario_id == Asset.id)
        .where(Asset.owner_id == owner_id, Asset.type == AssetType.SCENARIO)
        .group_by(Asset.id, Asset.title)
        .having(or_(total > 0, func.coalesce(published, False)))
        .order_by(recent.desc(), total.desc(), Asset.title, Asset.id)
    )
    return [(row[0], row[1], row[2], row[3]) for row in (await session.execute(query)).all()]
