# trpg-server/app/assets/scenarios/mine.py

"""
내 시나리오 목록(#1165). 줄마다 쓰인 수와 관심 수, 공개 상태를 함께 읽는다. SQL 은 이 파일에만 있다.

  - 쓰인 수(start_count)는 그 시나리오로 연 테이블의 모든 수다. 끝난 테이블도 센다(공개 목록의 카드와 같다,
    app/listings/popularity.py). 공개하지 않고 자기만 연 테이블도 센다
  - 관심 수(heart_count)는 공개 정보의 것이다. 공개 정보를 쓰지 않았으면 0 이다. 공개를 내려도 남는다
  - 차례: created(최근에 만든 것부터, 기본, 그 전부터의 차례), updated(최근에 고친 것부터),
    started(쓰인 수가 많은 것부터, 같으면 최근에 고친 것부터). 끝은 늘 id 라 같은 값끼리도 쪽이 흔들리지 않는다
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, Scenario
from app.assets.repository import owned
from app.listings.models import Listing
from app.tables.models import GameTable


class MineOrder(enum.StrEnum):
    """내 시나리오 목록의 차례(#1165)."""

    CREATED = 'created'
    UPDATED = 'updated'
    STARTED = 'started'


@dataclass(frozen=True)
class MyScenario:
    """내 시나리오 목록의 한 줄. 시나리오와 그 수들, 공개 상태다."""

    scenario: Scenario
    start_count: int
    heart_count: int
    # 공개한 시각. 공개하지 않았으면 None 이다
    published_at: datetime | None
    # 링크 공개(#993)인가. 공개 정보를 쓰지 않았으면 거짓이다
    unlisted: bool


def start_totals():
    """시나리오마다 연 테이블의 모든 수를 세는 부분 쿼리."""
    return select(GameTable.scenario_id, func.count().label('total')).group_by(GameTable.scenario_id).subquery()


def order_by(order: MineOrder, starts) -> tuple:
    """그 차례의 열들."""
    if order == MineOrder.STARTED:
        return (func.coalesce(starts.c.total, 0).desc(), Asset.updated_at.desc(), Asset.id)
    if order == MineOrder.UPDATED:
        return (Asset.updated_at.desc(), Asset.id)
    return (Asset.created_at.desc(), Asset.id)


async def list_mine(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int, order: MineOrder
) -> list[MyScenario]:
    """한 사람의 지우지 않은 시나리오의 한 쪽. 수와 공개 상태를 한 번의 쿼리로 읽는다."""
    starts = start_totals()
    query = (
        owned(Scenario, owner_id)
        .add_columns(
            func.coalesce(starts.c.total, 0),
            func.coalesce(Listing.heart_count, 0),
            Listing.published_at,
            func.coalesce(Listing.unlisted, False),
        )
        .outerjoin(starts, starts.c.scenario_id == Scenario.asset_id)
        .outerjoin(Listing, Listing.scenario_id == Scenario.asset_id)
        .order_by(*order_by(order, starts))
        .limit(limit)
        .offset(offset)
    )
    rows = await session.execute(query)
    return [MyScenario(row[0], row[1], row[2], row[3], row[4]) for row in rows.all()]
