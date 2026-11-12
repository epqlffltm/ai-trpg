# story-server/tests/test_db_limits.py

"""
DB 의 시간 한도(#1260)가 실제 연결에 걸리는지 본다. 실제 DB 에서 돈다.

한도가 없으면 멈춘 트랜잭션 하나 뒤에 줄을 선 요청들이 풀의 연결을 하나씩 쥐고 끝없이 기다린다.
값과 변환은 공용 코드의 테스트(shared/server-core/tests/test_database_and_jobs.py)가 본다. 여기서는 이 서버가 만든
연결에 그 값이 붙었는지와, DB 가 그 한도로 실제로 끊는지를 본다.

보는 것.
  - 서버의 연결: 잠금, 쿼리, 쉬는 트랜잭션의 한도가 설정의 값이다
  - 한도보다 오래 도는 쿼리는 끊긴다(57014). 잠금을 한도보다 오래 기다리면 그만둔다(55P03)
  - 마이그레이션과 스크립트의 연결(NO_LIMITS): 한도가 없다
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from server_core.database import LOCK_NOT_AVAILABLE, NO_LIMITS, QUERY_CANCELED, Limits, create_engine, is_db_timeout
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import EXTRA_SCHEMAS
from tests.conftest import make_test_settings

LIMIT_NAMES = ('lock_timeout', 'statement_timeout', 'idle_in_transaction_session_timeout')
READ_LIMITS = text('SELECT name, setting::int FROM pg_settings WHERE name = ANY(:names)')
# 한도를 넘기려고 쓰는 짧은 한도(밀리초)와 그보다 긴 쿼리(초)
SHORT_MS = 200
LONG_SECONDS = 5


@asynccontextmanager
async def engine_with(limits: Limits | None = None, **overrides) -> AsyncIterator[AsyncEngine]:
    """그 한도로 만든 엔진. 나가면 연결을 닫는다."""
    engine = create_engine(make_test_settings(**overrides), EXTRA_SCHEMAS, limits=limits)
    try:
        yield engine
    finally:
        await engine.dispose()


async def read_limits(connection) -> dict[str, int]:
    """그 연결에 걸린 한도들(밀리초)."""
    rows = await connection.execute(READ_LIMITS, {'names': list(LIMIT_NAMES)})
    return {name: value for name, value in rows}


def code_of(error: DBAPIError) -> str:
    """DB 가 준 오류 코드(SQLSTATE)."""
    # 드라이버의 오류가 코드를 덧붙여 갖는다. 타입에는 없는 칸이다
    return vars(error.orig)['sqlstate']


async def test_the_servers_connections_carry_the_limits(session: AsyncSession):
    settings = make_test_settings()

    limits = await read_limits(session)

    assert limits == {
        'lock_timeout': settings.db_lock_timeout_ms,
        'statement_timeout': settings.db_statement_timeout_ms,
        'idle_in_transaction_session_timeout': settings.db_idle_in_transaction_timeout_ms,
    }
    assert all(value > 0 for value in limits.values())


async def test_a_query_longer_than_the_limit_is_cut():
    async with engine_with(db_statement_timeout_ms=SHORT_MS) as engine, engine.connect() as connection:
        with pytest.raises(DBAPIError) as raised:
            await connection.execute(text('SELECT pg_sleep(:seconds)'), {'seconds': LONG_SECONDS})

    assert code_of(raised.value) == QUERY_CANCELED
    assert is_db_timeout(raised.value)


async def test_waiting_for_a_lock_gives_up_at_the_limit():
    """앞의 트랜잭션이 잠금을 쥔 채 멈춰 있어도, 뒤의 연결은 한도까지만 기다린다."""
    lock = text('SELECT pg_advisory_xact_lock(1260)')
    limited = engine_with(db_lock_timeout_ms=SHORT_MS)
    async with limited as engine, engine.connect() as holder, engine.connect() as waiter:
        await holder.execute(lock)
        with pytest.raises(DBAPIError) as raised:
            await waiter.execute(lock)

    assert code_of(raised.value) == LOCK_NOT_AVAILABLE
    assert is_db_timeout(raised.value)


async def test_migrations_and_scripts_connect_without_limits():
    async with engine_with(NO_LIMITS) as engine, engine.connect() as connection:
        limits = await read_limits(connection)

    assert limits == dict.fromkeys(LIMIT_NAMES, 0)
