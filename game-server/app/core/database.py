# game-server/app/core/database.py

"""
DB 연결. 엔진과 세션을 만들고, 요청마다 세션 하나를 내준다. 테이블 모델의 부모(Base)도 여기 있다.

엔진은 연결들의 묶음(풀)을 관리한다. 앱에 하나만 둔다.
세션은 작업 한 묶음(트랜잭션)의 단위다. 요청마다 새로 만들고 요청이 끝나면 닫는다.
"""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(DeclarativeBase):
    """
    모든 테이블 모델의 부모.

    이 클래스를 물려받은 모델은 Base.metadata 에 등록된다.
    Alembic 이 그 목록과 실제 DB 를 비교해 마이그레이션을 만든다.
    """


# DB 에 연결을 맺을 때 기다리는 최대 시간(초).
# DB 가 응답하지 않을 때 요청이 오래 매달리지 않게 한다
CONNECT_TIMEOUT_SECONDS = 5


def create_engine(settings: Settings) -> AsyncEngine:
    """
    엔진을 만든다. 이때는 DB 에 연결하지 않는다. 처음 쓸 때 연결한다.

    search_path 는 "스키마 이름 없이 테이블을 부르면 어느 스키마에서 찾는가" 다.
    연결할 때마다 설정의 스키마로 맞춘다. 그래서 코드에 스키마 이름을 적지 않아도 되고,
    테스트는 설정만 바꿔서 테스트용 스키마를 쓴다.
    """
    return create_async_engine(
        settings.database_url,
        connect_args={
            'timeout': CONNECT_TIMEOUT_SECONDS,
            'server_settings': {'search_path': settings.db_schema},
        },
        # 풀에서 꺼낸 연결이 살아 있는지 먼저 확인한다.
        # DB 가 재시작된 뒤에 끊긴 연결을 그대로 쓰다가 실패하는 것을 막는다
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    세션을 찍어 내는 틀을 만든다.

    expire_on_commit=False: 커밋한 뒤에도 객체의 값을 그대로 읽을 수 있게 한다.
    기본값(True)은 커밋 뒤에 값을 다시 읽으려고 DB 에 묻는데, async 에서는 그 조회가
    await 없이 일어나 오류가 난다.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """
    요청 하나가 쓸 세션을 내준다. FastAPI 의 의존성으로 쓴다.

    요청이 끝나면 세션을 닫는다. 예외가 나서 끝나도 닫힌다.
    커밋은 여기서 하지 않는다. 어디까지가 한 묶음인지는 작업을 하는 쪽이 안다.
    """
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


async def ping_database(session: AsyncSession) -> None:
    """DB 가 요청에 응답하는지 확인한다. 응답하지 않으면 예외가 난다."""
    await session.execute(text('SELECT 1'))
