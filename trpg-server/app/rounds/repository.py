# trpg-server/app/rounds/repository.py

"""
라운드를 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

누가 볼 수 있는가는 서비스가 판단한다. 여기의 함수는 모두 테이블의 ID 를 받는다.
라운드를 번호로 찾을 때도 "이 테이블의" 번호로 찾는다. 다른 테이블의 라운드가 딸려 나올 길이 없다.
되돌린 라운드(#288)는 읽지 않는다(LIVE). 그 번호는 다시 연 라운드의 것이다. 되돌린 라운드는 기록으로만 남는다.

닫기 직전의 게임 상태(round_snapshots)를 찍고 덮는 것도 여기에 있다(read_state, replace_state).
무엇을 찍는지는 app/rounds/snapshots.py 가 정한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, RowMapping, Table, delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.rounds.models import Round, RoundSnapshot
from app.rounds.snapshots import PARENT_SCOPES, STATE_COLUMNS, rows_of, state_tables, table_values_of
from app.tables.models import GameTable, TableStatus

# 되돌리지 않은 라운드라는 조건(uq_table_rounds_number 의 조건과 같다)
LIVE = Round.reverted_at.is_(None)


def add_round(session: AsyncSession, round_: Round) -> None:
    """새 라운드를 세션에 올린다."""
    session.add(round_)


async def find_latest_round(session: AsyncSession, table_id: uuid.UUID) -> Round | None:
    """
    테이블의 가장 최근 라운드를 찾는다. 아직 시작하지 않았으면 None.

    populate_existing: 세션이 이미 들고 있던 객체가 있어도 지금 읽은 값으로 덮어쓴다.
    테이블을 잠근 뒤에 부르므로, 여기서 읽은 것이 가장 새로운 값이다.
    """
    query = select(Round).where(Round.table_id == table_id, LIVE).order_by(Round.number.desc()).limit(1)
    return await session.scalar(query.execution_options(populate_existing=True))


async def find_round(session: AsyncSession, table_id: uuid.UUID, number: int) -> Round | None:
    """테이블의 라운드 하나를 번호로 찾는다. 없으면 None."""
    query = select(Round).where(Round.table_id == table_id, Round.number == number, LIVE)
    # 테이블을 잠근 뒤에 부를 때, 잠그기 전에 읽어 둔 낡은 값으로 판단하지 않게 한다
    return await session.scalar(query.execution_options(populate_existing=True))


async def list_rounds(session: AsyncSession, table_id: uuid.UUID, limit: int, offset: int) -> list[Round]:
    """테이블의 라운드를 처음 것부터 돌려준다. 지나간 이야기를 순서대로 읽는다."""
    query = select(Round).where(Round.table_id == table_id, LIVE).order_by(Round.number).limit(limit).offset(offset)
    return list(await session.scalars(query))


async def list_rounds_before(session: AsyncSession, table_id: uuid.UUID, number: int, limit: int) -> list[Round]:
    """
    이 번호 앞의 라운드를 최근 것부터 limit 개 골라, 오래된 것부터 돌려준다. 서술자에게 줄 지난 기록이다.

    최근 것부터 골라야 limit 개가 "가장 가까운 과거"가 된다. 돌려줄 때는 이야기의 순서로 뒤집는다.
    """
    query = (
        select(Round)
        .where(Round.table_id == table_id, Round.number < number, LIVE)
        .order_by(Round.number.desc())
        .limit(limit)
    )
    return list(reversed(list(await session.scalars(query))))


async def find_overdue_table_ids(session: AsyncSession, now: datetime, limit: int) -> list[uuid.UUID]:
    """
    마감이 지났는데 아직 선언을 받는 라운드의 테이블들. 마감이 이른 것부터 limit 개.

    잠그지 않는다. 고른 뒤 테이블을 잠그고 다시 본다(app/rounds/service.py 의 close_on_time).
    색인(ix_table_rounds_open_deadline)이 열린 라운드만 담는다.
    """
    query = (
        select(Round.table_id)
        .where(Round.closed_at.is_(None), Round.closing_at.is_(None), Round.deadline_at <= now)
        .order_by(Round.deadline_at)
        .limit(limit)
    )
    return list(await session.scalars(query))


async def find_vanished_table_ids(session: AsyncSession, before: datetime, limit: int) -> list[uuid.UUID]:
    """
    서술을 맡은 작업이 사라진 것으로 보이는 라운드의 테이블들. 오래된 것부터 limit 개.

    진행 중인 테이블의 닫는 중인 라운드 중에서, 서술의 실패를 적지 않았고 before 보다 먼저 닫기 시작한 것이다.
    잠그지 않는다. 고른 뒤 테이블을 잠그고 다시 본다(app/rounds/recovery.py).
    끝난 테이블은 빼야 한다. 끝난 테이블의 닫는 중인 라운드는 그대로 남아서, 빼지 않으면 바퀴마다 다시 고른다.
    닫히지 않은 라운드는 테이블마다 하나뿐이라(uq_table_rounds_open) 훑는 양이 열린 테이블의 수를 넘지 않는다.
    """
    query = (
        select(Round.table_id)
        .join(GameTable, GameTable.id == Round.table_id)
        .where(
            Round.closed_at.is_(None),
            Round.closing_at <= before,
            Round.narration_failed_at.is_(None),
            GameTable.status == TableStatus.PLAYING,
        )
        .order_by(Round.closing_at)
        .limit(limit)
    )
    return list(await session.scalars(query))


async def count_rounds(session: AsyncSession, table_id: uuid.UUID) -> int:
    """테이블의 라운드가 몇 개인지 센다."""
    query = select(func.count()).select_from(Round).where(Round.table_id == table_id, LIVE)
    return await session.scalar(query) or 0


# --- 닫기 직전의 게임 상태(#288) ---


def in_table(table: Table, table_id: uuid.UUID) -> ColumnElement[bool]:
    """표의 행 중 이 테이블의 것이라는 조건. 테이블의 id 가 없는 표는 가리키는 표의 행으로 고른다(PARENT_SCOPES)."""
    if table.name in PARENT_SCOPES:
        column, parent_name = PARENT_SCOPES[table.name]
        parent = Base.metadata.tables[parent_name]
        return table.c[column].in_(select(parent.c.id).where(parent.c.table_id == table_id))
    return table.c.table_id == table_id


async def read_state(session: AsyncSession, table_id: uuid.UUID) -> tuple[dict[str, list[RowMapping]], dict]:
    """
    테이블의 게임 상태를 읽는다. 표 이름에서 그 테이블의 행들로, 그리고 테이블의 행의 장의 값이다.

    행은 기본 키의 차례다. 세션이 들고 있는 바꾼 것은 먼저 DB 에 보낸다(읽기 전에 저절로).
    """
    rows = {}
    for table in state_tables():
        query = select(table).where(in_table(table, table_id)).order_by(*table.primary_key.columns)
        rows[table.name] = list((await session.execute(query)).mappings())
    columns = [GameTable.__table__.c[name] for name in STATE_COLUMNS]
    values = (await session.execute(select(*columns).where(GameTable.id == table_id))).mappings().one()
    return rows, dict(values)


async def save_snapshot(session: AsyncSession, table_id: uuid.UUID, round_id: uuid.UUID, state: dict) -> None:
    """테이블의 사진을 적는다. 이미 있으면 덮는다(테이블마다 하나)."""
    query = upsert(RoundSnapshot).values(table_id=table_id, round_id=round_id, state=state)
    query = query.on_conflict_do_update(
        index_elements=[RoundSnapshot.table_id],
        set_={'round_id': round_id, 'state': state, 'taken_at': func.now()},
    )
    await session.execute(query)


async def find_snapshot(session: AsyncSession, table_id: uuid.UUID) -> RoundSnapshot | None:
    """테이블의 사진. 없으면 None."""
    query = select(RoundSnapshot).where(RoundSnapshot.table_id == table_id)
    return await session.scalar(query.execution_options(populate_existing=True))


async def replace_state(session: AsyncSession, table_id: uuid.UUID, state: dict) -> None:
    """
    테이블의 게임 상태를 찍은 것으로 덮는다. 표마다 그 테이블의 행을 모두 지우고 찍은 행을 넣는다.

    가리키는 표부터 지우고, 가리켜지는 표부터 넣는다. 세션이 들고 있는 그 표들의 객체는 낡는다.
    부른 쪽이 저장한 뒤 세션을 비우고 다시 읽는다.
    """
    tables = state_tables()
    for table in reversed(tables):
        await session.execute(delete(table).where(in_table(table, table_id)))
    for table in tables:
        rows = rows_of(state, table)
        if rows:
            await session.execute(insert(table), rows)
    await session.execute(update(GameTable).where(GameTable.id == table_id).values(**table_values_of(state)))
