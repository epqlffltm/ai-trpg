# game-server/app/rounds/repository.py

"""
라운드를 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

누가 볼 수 있는가는 서비스가 판단한다. 여기의 함수는 모두 테이블의 ID 를 받는다.
라운드를 번호로 찾을 때도 "이 테이블의" 번호로 찾는다. 다른 테이블의 라운드가 딸려 나올 길이 없다.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds.models import Round


def add_round(session: AsyncSession, round_: Round) -> None:
    """새 라운드를 세션에 올린다."""
    session.add(round_)


async def find_latest_round(session: AsyncSession, table_id: uuid.UUID) -> Round | None:
    """
    테이블의 가장 최근 라운드를 찾는다. 아직 시작하지 않았으면 None.

    populate_existing: 세션이 이미 들고 있던 객체가 있어도 지금 읽은 값으로 덮어쓴다.
    테이블을 잠근 뒤에 부르므로, 여기서 읽은 것이 가장 새로운 값이다.
    """
    query = select(Round).where(Round.table_id == table_id).order_by(Round.number.desc()).limit(1)
    return await session.scalar(query.execution_options(populate_existing=True))


async def find_round(session: AsyncSession, table_id: uuid.UUID, number: int) -> Round | None:
    """테이블의 라운드 하나를 번호로 찾는다. 없으면 None."""
    query = select(Round).where(Round.table_id == table_id, Round.number == number)
    # 테이블을 잠근 뒤에 부를 때, 잠그기 전에 읽어 둔 낡은 값으로 판단하지 않게 한다
    return await session.scalar(query.execution_options(populate_existing=True))


async def list_rounds(session: AsyncSession, table_id: uuid.UUID, limit: int, offset: int) -> list[Round]:
    """테이블의 라운드를 처음 것부터 돌려준다. 지나간 이야기를 순서대로 읽는다."""
    query = select(Round).where(Round.table_id == table_id).order_by(Round.number).limit(limit).offset(offset)
    return list(await session.scalars(query))


async def count_rounds(session: AsyncSession, table_id: uuid.UUID) -> int:
    """테이블의 라운드가 몇 개인지 센다."""
    query = select(func.count()).select_from(Round).where(Round.table_id == table_id)
    return await session.scalar(query) or 0
