# trpg-server/app/assets/campaigns/repository.py

"""
캠페인의 판과, 편이 가리키는 시나리오의 판을 DB 에서 읽고 쓴다. 커밋하지 않는다.

캠페인 자신은 공통 저장소(app/assets/repository.py)가 다룬다.
여기의 함수는 "누구의 것인가"를 묻지 않는다. 캠페인과 시나리오가 그 사람의 것인지는 서비스가 먼저 확인한다.
판을 고치거나 지우는 함수는 없다.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.campaigns.models import CampaignVersion
from app.assets.models import ScenarioVersion


def add_version(session: AsyncSession, version: CampaignVersion) -> None:
    """새 판을 세션에 올린다."""
    session.add(version)


async def last_number(session: AsyncSession, campaign_id: uuid.UUID) -> int:
    """캠페인의 가장 큰 판 번호. 판이 없으면 0 이다."""
    query = select(func.max(CampaignVersion.number)).where(CampaignVersion.campaign_id == campaign_id)
    return await session.scalar(query) or 0


async def list_versions(session: AsyncSession, campaign_id: uuid.UUID) -> list[CampaignVersion]:
    """캠페인의 판을 최근 것부터 전부 돌려준다."""
    query = (
        select(CampaignVersion)
        .where(CampaignVersion.campaign_id == campaign_id)
        .order_by(CampaignVersion.number.desc())
    )
    return list(await session.scalars(query))


async def find_version(session: AsyncSession, campaign_id: uuid.UUID, number: int) -> CampaignVersion | None:
    """캠페인의 판 하나를 번호로 찾는다. 없으면 None."""
    query = select(CampaignVersion).where(CampaignVersion.campaign_id == campaign_id, CampaignVersion.number == number)
    return await session.scalar(query)


async def last_scenario_numbers(session: AsyncSession, scenario_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """시나리오마다 가장 큰 판 번호. 판이 없는 시나리오는 빠진다."""
    if not scenario_ids:
        return {}
    query = (
        select(ScenarioVersion.scenario_id, func.max(ScenarioVersion.number))
        .where(ScenarioVersion.scenario_id.in_(scenario_ids))
        .group_by(ScenarioVersion.scenario_id)
    )
    return {scenario_id: number for scenario_id, number in (await session.execute(query)).all()}


async def scenario_snapshot(session: AsyncSession, scenario_id: uuid.UUID, number: int) -> dict | None:
    """시나리오의 판 하나의 굳힌 문서. 없으면 None. 읽는 쪽이 지금의 모양으로 올려 읽는다(read_snapshot)."""
    query = select(ScenarioVersion.snapshot).where(
        ScenarioVersion.scenario_id == scenario_id, ScenarioVersion.number == number
    )
    return await session.scalar(query)
