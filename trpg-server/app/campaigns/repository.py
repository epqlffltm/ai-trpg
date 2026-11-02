# trpg-server/app/campaigns/repository.py

"""
캠페인의 플레이를 DB 에서 읽고 쓴다. 커밋하지 않는다. 누구의 것인지는 서비스가 본다.
"""

import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.campaigns.models import CampaignVersion
from app.campaigns.models import CampaignCarry, CampaignQuestResult, CampaignRun, CampaignSeat, CampaignTable
from app.tables.models import TableMember


def add(
    session: AsyncSession, row: CampaignRun | CampaignTable | CampaignCarry | CampaignQuestResult | CampaignSeat
) -> None:
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


async def table_at(session: AsyncSession, run_id: uuid.UUID, position: int) -> CampaignTable | None:
    """플레이의 그 편의 테이블. 아직 열지 않았으면 None."""
    query = select(CampaignTable).where(CampaignTable.run_id == run_id, CampaignTable.position == position)
    return await session.scalar(query)


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


async def delete_carries_of(session: AsyncSession, user_id: uuid.UUID) -> None:
    """그 사람의 넘길 것을 모두 지운다(탈퇴). 그것으로 앉은 자리의 표시(campaign_seats)도 함께 지워진다."""
    await session.execute(delete(CampaignCarry).where(CampaignCarry.user_id == user_id))


def runs_of(user_id: uuid.UUID):
    """그 사람의 플레이를 고르는 조건. 연 사람이거나, 그 플레이의 테이블에 앉아 있거나, 넘긴 것이 있다."""
    seated = (
        select(CampaignTable.run_id)
        .join(TableMember, TableMember.table_id == CampaignTable.table_id)
        .where(TableMember.user_id == user_id)
    )
    carried = select(CampaignCarry.run_id).where(CampaignCarry.user_id == user_id)
    return or_(CampaignRun.host_id == user_id, CampaignRun.id.in_(seated), CampaignRun.id.in_(carried))


async def list_runs_of(session: AsyncSession, user_id: uuid.UUID, limit: int, offset: int) -> list[CampaignRun]:
    """그 사람의 플레이의 한 쪽. 최근에 시작한 것부터."""
    query = (
        select(CampaignRun)
        .where(runs_of(user_id))
        .order_by(CampaignRun.created_at.desc(), CampaignRun.id)
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(query))


async def count_runs_of(session: AsyncSession, user_id: uuid.UUID) -> int:
    """그 사람의 플레이의 수."""
    return await session.scalar(select(func.count()).select_from(CampaignRun).where(runs_of(user_id))) or 0


async def versions_of(session: AsyncSession, version_ids: list[uuid.UUID]) -> dict[uuid.UUID, CampaignVersion]:
    """판들을 한 번에 읽는다. id → 판."""
    if not version_ids:
        return {}
    query = select(CampaignVersion).where(CampaignVersion.id.in_(version_ids))
    return {version.id: version for version in await session.scalars(query)}


async def current_tables(session: AsyncSession, runs: list[CampaignRun]) -> dict[uuid.UUID, uuid.UUID]:
    """플레이마다 지금 편의 테이블. 아직 열지 않은 플레이는 빠진다. 플레이의 id → 테이블의 id."""
    if not runs:
        return {}
    positions = {run.id: run.position for run in runs}
    query = select(CampaignTable).where(CampaignTable.run_id.in_(positions))
    links = await session.scalars(query)
    return {link.run_id: link.table_id for link in links if positions[link.run_id] == link.position}
