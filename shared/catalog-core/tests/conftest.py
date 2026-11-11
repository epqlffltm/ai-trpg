# shared/catalog-core/tests/conftest.py

"""
테스트마다 새 메모리 DB(SQLite)와 세션. 표는 tests/tables.py 의 것이다.

SQLite 는 소수(Numeric)를 제 모양으로 담지 못한다고 경고한다(pyproject.toml 에서 그 경고만 끈다).
값은 소수 여섯째 자리까지라 맞게 돌아온다.
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.tables import Base


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # 메모리 DB 는 연결마다 따로라, 연결 하나를 모두가 함께 쓴다
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as opened:
        yield opened
