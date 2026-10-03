# game-server/app/main.py

"""
게임 서버의 시작점. FastAPI 앱을 만들고 라우터를 붙인다.

    uv run uvicorn app.main:app --port 8001 --reload
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, readiness
from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory

# 이 서버의 API 가 놓이는 주소. 인증 서버는 /api/v1/auth 를 쓴다
API_PREFIX = '/api/v1/game'


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    서버가 뜰 때와 꺼질 때 할 일. yield 앞이 뜰 때, 뒤가 꺼질 때다.

    꺼질 때 DB 연결을 전부 닫는다. 닫지 않으면 DB 쪽에 끊긴 연결이 한동안 남는다.
    """
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    FastAPI 앱을 만들어 돌려준다.

    모듈을 불러올 때 바로 만들지 않고 함수로 둔다.
    테스트가 설정을 바꿔 가며 앱을 여러 개 만들 수 있다.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title='AI TRPG 게임 서버',
        # API 문서 화면은 개발할 때만 연다. 운영 서버에서는 API 의 구조를 내보이지 않는다
        docs_url=f'{API_PREFIX}/docs' if settings.debug else None,
        redoc_url=None,
        openapi_url=f'{API_PREFIX}/openapi.json' if settings.debug else None,
        lifespan=lifespan,
    )

    # 엔진과 세션 틀을 앱에 붙여 둔다. 전역 변수로 두지 않는다.
    # 앱마다 자기 엔진을 가지므로, 테스트가 다른 설정의 앱을 만들어도 서로 섞이지 않는다.
    # 엔진을 만드는 것만으로는 DB 에 연결하지 않는다
    app.state.engine = create_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)

    # 상태를 확인하는 주소는 API 주소 밖에 둔다. 프록시와 관리 도구가 부르는 것이라 버전이 없다
    app.include_router(health.router)
    app.include_router(readiness.router)

    return app


app = create_app()
