# game-server/app/assets/scenarios/repository.py

"""
시나리오의 판을 DB 에서 읽고 쓴다. 커밋하지 않는다.

시나리오 자신은 공통 저장소(app/assets/repository.py)가 다룬다.
여기의 함수는 "누구의 것인가"를 묻지 않는다. 시나리오가 그 사람의 것인지는 서비스가 먼저 확인한다.
대신 모든 함수가 시나리오의 ID 를 받는다. 판은 언제나 "어느 시나리오의 것인가"와 함께 찾는다.

판을 고치거나 지우는 함수는 없다.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import ScenarioVersion


def add_version(session: AsyncSession, version: ScenarioVersion) -> None:
    """새 판을 세션에 올린다."""
    session.add(version)


async def last_number(session: AsyncSession, scenario_id: uuid.UUID) -> int:
    """시나리오의 가장 큰 판 번호. 판이 없으면 0 이다."""
    query = select(func.max(ScenarioVersion.number)).where(ScenarioVersion.scenario_id == scenario_id)
    return await session.scalar(query) or 0


async def list_versions(session: AsyncSession, scenario_id: uuid.UUID) -> list[ScenarioVersion]:
    """시나리오의 판을 최근 것부터 전부 돌려준다."""
    query = (
        select(ScenarioVersion)
        .where(ScenarioVersion.scenario_id == scenario_id)
        .order_by(ScenarioVersion.number.desc())
    )
    result = await session.scalars(query)
    return list(result)


async def find_version(session: AsyncSession, scenario_id: uuid.UUID, number: int) -> ScenarioVersion | None:
    """시나리오의 판 하나를 번호로 찾는다. 없으면 None."""
    query = select(ScenarioVersion).where(ScenarioVersion.scenario_id == scenario_id, ScenarioVersion.number == number)
    return await session.scalar(query)
