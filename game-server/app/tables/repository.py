# game-server/app/tables/repository.py

"""
테이블을 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

누가 볼 수 있는가(참가자인가, 방장인가)는 서비스가 판단한다. 여기는 찾아 주기만 한다.
로비만은 다르다. 누구나 보는 목록이라서 "보여도 되는 것"의 조건(open_to)을 조회 안에 넣는다.
"""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.assets.models import Rating, ScenarioVersion
from app.tables.models import GameTable, TableMember, TableNpc, TableStatus


def add_table(session: AsyncSession, table: GameTable) -> None:
    """새 테이블을 세션에 올린다. 앉은 사람(members)도 함께 올라간다."""
    session.add(table)


def add_npcs(session: AsyncSession, npcs: list[TableNpc]) -> None:
    """테이블의 NPC 상태들을 세션에 올린다. 테이블이 먼저 저장돼 있어야 한다."""
    session.add_all(npcs)


async def find_table(session: AsyncSession, table_id: uuid.UUID) -> GameTable | None:
    """테이블 하나를 찾는다. 읽기만 할 때 쓴다."""
    return await session.scalar(select(GameTable).where(GameTable.id == table_id))


def locked(query: Select[tuple[GameTable]]) -> Select[tuple[GameTable]]:
    """
    찾은 테이블을 이 트랜잭션이 끝날 때까지 혼자 잠근다.

    populate_existing: 세션이 이미 들고 있던 객체가 있어도, 잠근 뒤에 읽은 값으로 덮어쓴다.
    잠그기 전에 읽어 둔 낡은 값으로 판단하지 않게 한다.
    """
    return query.with_for_update().execution_options(populate_existing=True)


async def lock_table(session: AsyncSession, table_id: uuid.UUID) -> GameTable | None:
    """
    테이블 하나를 찾아 잠근다. 테이블을 바꾸는 일은 모두 이것으로 시작한다.

    같은 테이블을 바꾸려는 다른 요청은 이 트랜잭션이 끝날 때까지 기다린다.
    "자리가 남았나 보고 앉는다" 같은 일을 두 요청이 동시에 하지 못한다.
    """
    return await session.scalar(locked(select(GameTable).where(GameTable.id == table_id)))


async def lock_table_by_invite_code(session: AsyncSession, invite_code: str) -> GameTable | None:
    """초대 코드로 테이블을 찾아 잠근다. 들어갈 때 쓴다."""
    return await session.scalar(locked(select(GameTable).where(GameTable.invite_code == invite_code)))


async def reload_table(session: AsyncSession, table_id: uuid.UUID) -> GameTable:
    """
    저장한 테이블을 다시 읽는다. 커밋한 뒤에 쓴다.

    DB 가 정한 값(만든 시각, 들어온 시각)과 앉은 사람의 목록을 지금의 것으로 맞춘다.
    """
    query = select(GameTable).where(GameTable.id == table_id).execution_options(populate_existing=True)
    return (await session.execute(query)).scalar_one()


def seated(user_id: uuid.UUID) -> Select[tuple[GameTable]]:
    """이 사람이 앉아 있는 테이블을 고르는 조건."""
    return (
        select(GameTable).join(TableMember, TableMember.table_id == GameTable.id).where(TableMember.user_id == user_id)
    )


async def list_seated(session: AsyncSession, user_id: uuid.UUID, limit: int, offset: int) -> list[GameTable]:
    """
    이 사람이 앉아 있는 테이블을 최근에 만든 것부터 돌려준다.

    목록에는 판의 복사본(content)이 필요 없다. 큰 문서라서 읽어 오지 않는다.
    """
    query = seated(user_id).options(defer(GameTable.content))
    # 만든 시각이 같은 것끼리의 순서도 정해 둔다. 정하지 않으면 쪽을 넘길 때 같은 것이 두 번 나오거나 빠진다
    query = query.order_by(GameTable.created_at.desc(), GameTable.id).limit(limit).offset(offset)
    return list(await session.scalars(query))


async def count_seated(session: AsyncSession, user_id: uuid.UUID) -> int:
    """이 사람이 앉아 있는 테이블이 몇 개인지 센다."""
    return await session.scalar(select(func.count()).select_from(seated(user_id).subquery())) or 0


# --- 로비. 앉지 않은 사람이 보는 목록이다 ---


def open_to(allowed_ratings: list[Rating], scenario_id: uuid.UUID | None) -> Select[tuple[GameTable]]:
    """
    로비에 보여도 되는 테이블을 고르는 조건. 로비를 읽는 함수들이 함께 쓴다.

    로비에 보이기로 했고, 모집 중이고, 자리가 남았고, 보는 사람이 볼 수 있는 등급이어야 한다.
    scenario_id 를 주면 그 시나리오의 판으로 만든 테이블만 고른다.
    """
    # 테이블마다 앉은 사람을 세는 작은 조회. 바깥 조회의 테이블과 이어진다
    seats_taken = (
        select(func.count()).select_from(TableMember).where(TableMember.table_id == GameTable.id).scalar_subquery()
    )
    query = select(GameTable).where(
        GameTable.is_public,
        GameTable.status == TableStatus.RECRUITING,
        GameTable.rating.in_(allowed_ratings),
        seats_taken < GameTable.capacity,
    )
    if scenario_id is not None:
        query = query.join(ScenarioVersion, ScenarioVersion.id == GameTable.version_id).where(
            ScenarioVersion.scenario_id == scenario_id
        )
    return query


async def list_lobby(
    session: AsyncSession, allowed_ratings: list[Rating], scenario_id: uuid.UUID | None, limit: int, offset: int
) -> list[GameTable]:
    """로비에 보이는 테이블을 최근에 만든 것부터 돌려준다. 판의 복사본(content)은 읽어 오지 않는다."""
    query = open_to(allowed_ratings, scenario_id).options(defer(GameTable.content))
    query = query.order_by(GameTable.created_at.desc(), GameTable.id).limit(limit).offset(offset)
    return list(await session.scalars(query))


async def count_lobby(session: AsyncSession, allowed_ratings: list[Rating], scenario_id: uuid.UUID | None) -> int:
    """로비에 보이는 테이블이 몇 개인지 센다."""
    return await session.scalar(select(func.count()).select_from(open_to(allowed_ratings, scenario_id).subquery())) or 0
