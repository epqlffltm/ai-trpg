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

import logging
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import Any, cast

from fastapi import HTTPException, Request, status
from sqlalchemy import CursorResult, Result, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from server_core.observability.pool_metrics import MeteredPool
from server_core.settings import CoreSettings

logger = logging.getLogger(__name__)

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


# DB 가 시간 한도로 쿼리를 끊었을 때의 오류 코드(SQLSTATE). 결제 서버가 보는 것과 같다
LOCK_NOT_AVAILABLE = '55P03'  # lock_timeout 이 지났다
QUERY_CANCELED = '57014'  # statement_timeout 이 지났다
TIMEOUT_CODES = frozenset({LOCK_NOT_AVAILABLE, QUERY_CANCELED})
# 그때 로그에 남기는 오류 코드와, 응답에 싣는 "몇 초 뒤에 다시"(Retry-After)
DB_TIMEOUT_ERROR_CODE = 'db.timeout'
RETRY_AFTER_SECONDS = '1'


@dataclass(frozen=True)
class Limits:
    """
    DB 가 연결 하나를 붙잡아 두는 가장 긴 시간들(밀리초). 0 은 그 한도를 끈다.

    서버의 연결은 설정의 값(limits_of)을, 마이그레이션과 스크립트는 한도 없음(NO_LIMITS)을 쓴다.
    색인을 만들거나 표를 고치는 일은 오래 걸려도 되고, 도중에 끊기면 안 된다.
    """

    lock_timeout_ms: int = 0
    statement_timeout_ms: int = 0
    idle_in_transaction_timeout_ms: int = 0


# 한도 없음. 마이그레이션과 스크립트가 쓴다
NO_LIMITS = Limits()


def limits_of(settings: CoreSettings) -> Limits:
    """설정에 적힌 서버의 한도."""
    return Limits(
        lock_timeout_ms=settings.db_lock_timeout_ms,
        statement_timeout_ms=settings.db_statement_timeout_ms,
        idle_in_transaction_timeout_ms=settings.db_idle_in_transaction_timeout_ms,
    )


def limit_settings(limits: Limits) -> dict[str, str]:
    """한도를 연결을 맺을 때 DB 에 넘기는 설정으로 바꾼다. 단위 없는 숫자는 밀리초다. 0 도 그대로 넘겨 끈다."""
    return {
        'lock_timeout': str(limits.lock_timeout_ms),
        'statement_timeout': str(limits.statement_timeout_ms),
        'idle_in_transaction_session_timeout': str(limits.idle_in_transaction_timeout_ms),
    }


def search_path(schema: str, extra_schemas: Sequence[str] = ()) -> str:
    """
    연결의 search_path. 설정의 스키마가 먼저다. 이름 없이 만드는 테이블은 거기에 놓인다.

    extra_schemas 는 그 뒤에 둔다. 확장(pgvector)이 놓인 스키마처럼 이름 없이 쓰고 싶은 것이다(게임 서버의 extensions).
    """
    return ', '.join([schema, *extra_schemas])


def create_engine(
    settings: CoreSettings,
    extra_schemas: Sequence[str] = (),
    limits: Limits | None = None,
) -> AsyncEngine:
    """
    엔진을 만든다. 이때는 DB 에 연결하지 않는다. 처음 쓸 때 연결한다.

    search_path 는 "스키마 이름 없이 테이블을 부르면 어느 스키마에서 찾는가" 다.
    연결할 때마다 설정의 스키마로 맞춘다. 그래서 코드에 스키마 이름을 적지 않아도 되고,
    테스트는 설정만 바꿔서 테스트용 스키마를 쓴다.
    풀은 연결을 기다린 시간을 재는 것이다(MeteredPool). 크기는 설정(DB_POOL_SIZE, DB_MAX_OVERFLOW)에서 읽는다.
    그 밖은 SQLAlchemy 의 기본 풀과 같다.
    limits 는 연결마다 거는 시간 한도다(#1260). 주지 않으면 설정에 적힌 서버의 한도다.
    마이그레이션과 스크립트는 NO_LIMITS 를 준다.
    """
    limits = limits_of(settings) if limits is None else limits
    return create_async_engine(
        settings.database_url,
        connect_args={
            'timeout': CONNECT_TIMEOUT_SECONDS,
            'server_settings': {
                'search_path': search_path(settings.db_schema, extra_schemas),
                **limit_settings(limits),
            },
        },
        # 풀에서 꺼낸 연결이 살아 있는지 먼저 확인한다.
        # DB 가 재시작된 뒤에 끊긴 연결을 그대로 쓰다가 실패하는 것을 막는다
        pool_pre_ping=True,
        poolclass=MeteredPool,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
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


def is_db_timeout(error: DBAPIError) -> bool:
    """DB 가 시간 한도(잠금, 쿼리)로 끊은 오류인가. 드라이버의 오류에 적힌 코드(SQLSTATE)로 안다."""
    code = getattr(error.orig, 'sqlstate', None) or getattr(error.orig, 'pgcode', None)
    return code in TIMEOUT_CODES


def busy_response(error: DBAPIError) -> HTTPException:
    """DB 가 시간 한도로 끊었을 때의 응답. 503 과 "잠시 뒤에 다시"다. 무엇이 걸렸는지는 로그에만 남긴다."""
    logger.warning('DB 가 시간 한도로 쿼리를 끊었다', extra={'error_code': DB_TIMEOUT_ERROR_CODE})
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail='지금은 처리할 수 없습니다. 잠시 뒤에 다시 시도해 주세요.',
        headers={'Retry-After': RETRY_AFTER_SECONDS},
    )


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """
    요청 하나가 쓸 세션을 내준다. FastAPI 의 의존성으로 쓴다. 앱의 app.state.session_factory 를 쓴다.

    요청이 끝나면 세션을 닫는다. 예외가 나서 끝나도 닫힌다.
    커밋은 여기서 하지 않는다. 어디까지가 한 묶음인지는 작업을 하는 쪽이 안다.
    DB 가 시간 한도(잠금, 쿼리)로 끊은 요청은 503 으로 답한다(#1260). 그 쿼리는 적히지 않았다. 다시 보내면 된다.
    """
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        try:
            yield session
        except DBAPIError as error:
            if not is_db_timeout(error):
                raise
            raise busy_response(error) from error


def affected_rows(result: Result[Any]) -> int:
    """
    UPDATE, DELETE, INSERT 가 바꾼 줄의 수.

    session.execute 는 어느 문장이든 Result 로 적혀 있지만, 이 문장들의 결과는 커서의 결과(CursorResult)다.
    바꾼 줄의 수(rowcount)는 거기에만 있다. SELECT 의 결과에 쓰지 않는다.
    """
    return cast(CursorResult[Any], result).rowcount


async def ping_database(session: AsyncSession) -> None:
    """DB 가 요청에 응답하는지 확인한다. 응답하지 않으면 예외가 난다."""
    await session.execute(text('SELECT 1'))
