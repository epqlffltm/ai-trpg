# trpg-server/app/campaigns/repository.py

"""
캠페인의 플레이를 DB 에서 읽고 쓴다. 커밋하지 않는다. 누구의 것인지는 서비스가 본다.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaigns.models import CampaignCarry, CampaignQuestResult, CampaignRun, CampaignTable


def add(session: AsyncSession, row: CampaignRun | CampaignTable | CampaignCarry | CampaignQuestResult) -> None:
    """새 행을 세션에 올린다."""
    session.add(row)


async def find_run(session: AsyncSession, run_id: uuid.UUID) -> CampaignRun | None:
    """플레이 하나. 없으면 None."""
    return await session.get(CampaignRun, run_id)


async def lock_run(session: AsyncSession, run_id: uuid.UUID) -> CampaignRun | None:
    """플레이 하나를 혼자 잠근다. 편이 끝난 것을 적는 일과 다음 편을 여는 일이 겹치지 않게 한다. 없으면 None."""
    return await session.scalar(select(CampaignRun).where(CampaignRun.id == run_id).with_for_update())


async def find_link(session: AsyncSession, table_id: uuid.UUID) -> CampaignTable | None:
    """그 테이블이 어느 플레이의 몇 편인가. 캠페인의 테이블이 아니면 None."""
    return await session.get(CampaignTable, table_id)


async def run_tables(session: AsyncSession, run_id: uuid.UUID) -> list[CampaignTable]:
    """플레이의 편마다의 테이블. 편의 차례다."""
    query = select(CampaignTable).where(CampaignTable.run_id == run_id).order_by(CampaignTable.position)
    return list(await session.scalars(query))


async def carries_of(session: AsyncSession, run_id: uuid.UUID, position: int) -> list[CampaignCarry]:
    """그 편이 끝날 때 적은 넘길 것들."""
    query = select(CampaignCarry).where(CampaignCarry.run_id == run_id, CampaignCarry.position == position)
    return list(await session.scalars(query.order_by(CampaignCarry.created_at, CampaignCarry.id)))


async def last_carry(session: AsyncSession, run_id: uuid.UUID, user_id: uuid.UUID) -> CampaignCarry | None:
    """그 사람이 그 플레이에서 가장 나중에 넘긴 것. 없으면 None."""
    query = (
        select(CampaignCarry)
        .where(CampaignCarry.run_id == run_id, CampaignCarry.user_id == user_id)
        .order_by(CampaignCarry.position.desc())
        .limit(1)
    )
    return await session.scalar(query)


async def quest_results(session: AsyncSession, run_id: uuid.UUID) -> list[CampaignQuestResult]:
    """플레이의 편마다의 퀘스트 결과. 편의 차례다."""
    query = select(CampaignQuestResult).where(CampaignQuestResult.run_id == run_id)
    return list(await session.scalars(query.order_by(CampaignQuestResult.position, CampaignQuestResult.entry_id)))
