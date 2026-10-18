# game-server/app/operators/repository.py

"""
운영자 API 가 쓰는 SQL. 감사 기록을 적고, 남의 것을 주인을 가리지 않고 읽는다.

일반 API 의 저장소는 "자기 것"과 "앉아 있는 테이블"로 걸러 읽는다. 여기의 함수는 거르지 않는다.
그래서 운영자 API(app/operators/service.py) 말고는 부르지 않는다.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, Scenario
from app.operators.models import OperatorRead
from app.whispers.models import Whisper


def add_read(session: AsyncSession, read: OperatorRead) -> None:
    """감사 기록 한 줄을 세션에 올린다. 커밋은 부르는 쪽이 한다."""
    session.add(read)


async def find_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> Scenario | None:
    """누구의 것이든 지우지 않은 시나리오 하나를 찾는다. 없으면 None."""
    query = select(Scenario).join(Scenario.asset).where(Scenario.asset_id == scenario_id, Asset.deleted_at.is_(None))
    return await session.scalar(query)


def sent_copies(table_id: uuid.UUID):
    """
    테이블의 귓속말을 한 장씩 고르는 조건.

    쪽지는 보낸 사람과 받은 사람의 쪽지함에 한 장씩 적힌다. 보낸 사람의 쪽지함의 것만 고르면 한 장씩이다.
    """
    return Whisper.table_id == table_id, Whisper.owner_id == Whisper.sender_id


async def list_whispers(session: AsyncSession, table_id: uuid.UUID, limit: int, offset: int) -> list[Whisper]:
    """테이블의 귓속말 전부를 보낸 순서대로 돌려준다. 쪽지함이 아니라 테이블 전체라 번호가 아니라 offset 으로 넘긴다."""
    query = (
        select(Whisper)
        .where(*sent_copies(table_id))
        .order_by(Whisper.created_at, Whisper.id)
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(query))


async def count_whispers(session: AsyncSession, table_id: uuid.UUID) -> int:
    """테이블의 귓속말이 모두 몇 장인가."""
    query = select(func.count()).select_from(Whisper).where(*sent_copies(table_id))
    return await session.scalar(query) or 0
