# shared/reference-core/tests/conftest.py

"""
쿼리의 테스트가 쓰는 실제 PostgreSQL(pgvector). 접속 주소는 REFERENCE_CORE_TEST_DATABASE_URL 이다.

벡터의 거리(코사인)와 PostgreSQL 의 넣기(ON CONFLICT)를 쓰는 쿼리라 메모리의 SQLite 로는 볼 수 없다.
주소가 없으면 DB 의 테스트는 건너뛴다. CI(.github/workflows/shared.yml)는 pgvector 를 띄워 주소를 준다.
테스트마다 따로 된 스키마(reference_core_test)를 지우고 다시 만든다. 그 계정은 확장(vector)을 만들 수 있어야 한다.
"""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from tests.tables import Base

DATABASE_URL = os.environ.get('REFERENCE_CORE_TEST_DATABASE_URL', '')
SCHEMA = 'reference_core_test'
# 확장은 compose 에서는 extensions 스키마에, CI 의 새 DB 에서는 public 에 놓인다. 둘 다 본다
SEARCH_PATH = f'{SCHEMA}, extensions, public'


@pytest.fixture(scope='session')
async def engine() -> AsyncIterator[AsyncEngine]:
    if not DATABASE_URL:
        pytest.skip('REFERENCE_CORE_TEST_DATABASE_URL 이 없어 DB 의 테스트를 건너뛴다')
    made = create_async_engine(DATABASE_URL, connect_args={'server_settings': {'search_path': SEARCH_PATH}})
    async with made.begin() as connection:
        await connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
    yield made
    await made.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """비운 스키마에 표를 새로 만든다. 앞의 테스트가 남긴 것에 기대지 않는다."""
    async with engine.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA IF EXISTS {SCHEMA} CASCADE'))
        await connection.execute(text(f'CREATE SCHEMA {SCHEMA}'))
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as opened:
        yield opened
