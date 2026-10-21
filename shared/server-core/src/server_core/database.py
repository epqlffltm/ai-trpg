# shared/server-core/src/server_core/database.py

"""
DB 연결. 엔진과 세션을 만들고, 요청마다 세션 하나를 내준다.

엔진은 연결들의 묶음(풀)을 관리한다. 앱에 하나만 둔다.
세션은 작업 한 묶음(트랜잭션)의 단위다. 요청마다 새로 만들고 요청이 끝나면 닫는다.

테이블 모델의 부모(Base)는 서버마다 둔다(서버의 app/core/database.py). 한 서버의 표가 다른 서버의 마이그레이션에
섞이지 않게 한다. 이름을 짓는 규칙(NAMING_CONVENTION)만 여기서 함께 쓴다.

    class Base(DeclarativeBase):
        metadata = MetaData(naming_convention=NAMING_CONVENTION)
"""

from collections.abc import AsyncGenerator, Sequence
from typing import Any

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from server_core.observability.pool_metrics import MeteredPool
from server_core.settings import CoreSettings

# 제약과 색인의 이름을 짓는 규칙.
# 정해 두지 않으면 DB 가 제멋대로 이름을 붙이거나(색인, 외래 키) 이름 없이 만든다(CHECK).
# 이름을 모르면 나중에 마이그레이션에서 그 제약을 고치거나 지울 수 없다
NAMING_CONVENTION = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}

# DB 에 연결을 맺을 때 기다리는 최대 시간(초). DB 가 응답하지 않을 때 요청이 오래 매달리지 않게 한다
CONNECT_TIMEOUT_SECONDS = 5
# 풀이 늘 들고 있는 연결과, 붐빌 때 더 맺는 연결. SQLAlchemy 의 기본값을 적어 둔다.
# 둘의 합이 메트릭의 db_pool_connections_max 다(server_core/observability/pool_metrics.py).
# 서버마다 다르게 하려면 create_engine 에 넘긴다(#592 에서 서버마다의 한도를 정한다)
POOL_SIZE = 5
MAX_OVERFLOW = 10
POOL_MAX_CONNECTIONS = POOL_SIZE + MAX_OVERFLOW


def search_path(schema: str, extra_schemas: Sequence[str] = ()) -> str:
    """
    연결의 search_path. 설정의 스키마가 먼저다. 이름 없이 만드는 테이블은 거기에 놓인다.

    extra_schemas 는 그 뒤에 둔다. 확장(pgvector)이 놓인 스키마처럼 이름 없이 쓰고 싶은 것이다(게임 서버의 extensions).
    """
    return ', '.join([schema, *extra_schemas])


def create_engine(
    settings: CoreSettings,
    extra_schemas: Sequence[str] = (),
    pool_size: int = POOL_SIZE,
    max_overflow: int = MAX_OVERFLOW,
) -> AsyncEngine:
    """
    엔진을 만든다. 이때는 DB 에 연결하지 않는다. 처음 쓸 때 연결한다.

    search_path 는 "스키마 이름 없이 테이블을 부르면 어느 스키마에서 찾는가" 다.
    연결할 때마다 설정의 스키마로 맞춘다. 그래서 코드에 스키마 이름을 적지 않아도 되고,
    테스트는 설정만 바꿔서 테스트용 스키마를 쓴다.
    풀은 연결을 기다린 시간을 재는 것이다(MeteredPool). 그 밖은 SQLAlchemy 의 기본 풀과 같다.
    """
    return create_async_engine(
        settings.database_url,
        connect_args={
            'timeout': CONNECT_TIMEOUT_SECONDS,
            'server_settings': {'search_path': search_path(settings.db_schema, extra_schemas)},
        },
        # 풀에서 꺼낸 연결이 살아 있는지 먼저 확인한다.
        # DB 가 재시작된 뒤에 끊긴 연결을 그대로 쓰다가 실패하는 것을 막는다
        pool_pre_ping=True,
        poolclass=MeteredPool,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )


def create_session_factory(engine: AsyncEngine, info: dict[str, Any] | None = None) -> async_sessionmaker[AsyncSession]:
    """
    세션을 찍어 내는 틀을 만든다.

    expire_on_commit=False: 커밋한 뒤에도 객체의 값을 그대로 읽을 수 있게 한다.
    기본값(True)은 커밋 뒤에 값을 다시 읽으려고 DB 에 묻는데, async 에서는 그 조회가
    await 없이 일어나 오류가 난다.
    info: 세션마다 곁에 들고 다니는 것(session.info). 세션마다 이것의 복사본을 받는다(게임 서버의 신호의 서명자).
    """
    return async_sessionmaker(engine, expire_on_commit=False, info=info)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """
    요청 하나가 쓸 세션을 내준다. FastAPI 의 의존성으로 쓴다. 앱의 app.state.session_factory 를 쓴다.

    요청이 끝나면 세션을 닫는다. 예외가 나서 끝나도 닫힌다.
    커밋은 여기서 하지 않는다. 어디까지가 한 묶음인지는 작업을 하는 쪽이 안다.
    """
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


async def ping_database(session: AsyncSession) -> None:
    """DB 가 요청에 응답하는지 확인한다. 응답하지 않으면 예외가 난다."""
    await session.execute(text('SELECT 1'))
