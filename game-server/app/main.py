# game-server/app/main.py

"""
게임 서버의 시작점. FastAPI 앱을 만들고 라우터를 붙인다.

    uv run uvicorn app.main:app --port 8001 --reload
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api import health, me, readiness
from app.assets.lorebooks import router as lorebooks
from app.assets.lorebooks.service import LorebookFullError
from app.assets.routing import handle_asset_in_use, handle_asset_not_found, handle_asset_reference
from app.assets.rulebooks import router as rulebooks
from app.assets.scenarios import router as scenarios
from app.assets.scenarios.publishing import ScenarioNotReadyError
from app.assets.service import AssetInUseError, AssetNotFoundError, AssetReferenceError
from app.assets.worlds import router as worlds
from app.auth.jwks import JwksCache
from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory
from app.listings import router as listings
from app.listings.service import ListingNotReadyError
from app.tables import router as tables
from app.tables.service import (
    MemberNotFoundError,
    NotHostError,
    TableConflictError,
    TableNotFoundError,
    TableOptionError,
)

# 이 서버의 API 가 놓이는 주소. 인증 서버는 /api/v1/auth 를 쓴다
API_PREFIX = '/api/v1/game'


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    서버가 뜰 때와 꺼질 때 할 일. yield 앞이 뜰 때, 뒤가 꺼질 때다.

    꺼질 때 DB 연결과 인증 서버로 가는 연결을 전부 닫는다. 닫지 않으면 상대 쪽에 끊긴 연결이 한동안 남는다.
    """
    yield
    await app.state.engine.dispose()
    await app.state.http_client.aclose()


def create_app(settings: Settings | None = None, http_client: httpx.AsyncClient | None = None) -> FastAPI:
    """
    FastAPI 앱을 만들어 돌려준다.

    모듈을 불러올 때 바로 만들지 않고 함수로 둔다.
    테스트가 설정을 바꿔 가며 앱을 여러 개 만들 수 있다.

    http_client 는 다른 서버에 요청을 보낼 때 쓰는 클라이언트다.
    테스트가 가짜 인증 서버로 가는 클라이언트를 넣을 수 있게 밖에서 받는다.
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

    # 요청을 처리하는 코드가 설정을 꺼내 쓸 수 있게 앱에 붙여 둔다
    app.state.settings = settings

    # 엔진과 세션 틀을 앱에 붙여 둔다. 전역 변수로 두지 않는다.
    # 앱마다 자기 엔진을 가지므로, 테스트가 다른 설정의 앱을 만들어도 서로 섞이지 않는다.
    # 엔진을 만드는 것만으로는 DB 에 연결하지 않는다
    app.state.engine = create_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)

    # 인증 서버의 공개키를 기억하는 곳. 앱에 하나만 두고 모든 요청이 함께 쓴다.
    # 만드는 것만으로는 인증 서버에 요청을 보내지 않는다. 처음 토큰을 검증할 때 가져온다
    app.state.http_client = http_client or httpx.AsyncClient()
    app.state.jwks = JwksCache(app.state.http_client, settings.auth_jwks_url)

    # 상태를 확인하는 주소는 API 주소 밖에 둔다. 프록시와 관리 도구가 부르는 것이라 버전이 없다
    app.include_router(health.router)
    app.include_router(readiness.router)

    app.include_router(me.router, prefix=API_PREFIX)
    app.include_router(worlds.router, prefix=API_PREFIX)
    app.include_router(rulebooks.router, prefix=API_PREFIX)
    app.include_router(scenarios.router, prefix=API_PREFIX)
    app.include_router(lorebooks.router, prefix=API_PREFIX)
    app.include_router(listings.owner_router, prefix=API_PREFIX)
    app.include_router(listings.public_router, prefix=API_PREFIX)
    app.include_router(tables.router, prefix=API_PREFIX)

    # 서비스가 던지는 예외를 HTTP 응답으로 바꾸는 곳. API 함수마다 try 를 쓰지 않는다
    app.add_exception_handler(AssetNotFoundError, handle_asset_not_found)
    app.add_exception_handler(AssetInUseError, handle_asset_in_use)
    app.add_exception_handler(AssetReferenceError, handle_asset_reference)
    app.add_exception_handler(LorebookFullError, lorebooks.handle_lorebook_full)
    app.add_exception_handler(ScenarioNotReadyError, scenarios.handle_scenario_not_ready)
    app.add_exception_handler(ListingNotReadyError, listings.handle_listing_not_ready)
    app.add_exception_handler(TableNotFoundError, tables.handle_table_not_found)
    app.add_exception_handler(MemberNotFoundError, tables.handle_member_not_found)
    app.add_exception_handler(NotHostError, tables.handle_not_host)
    app.add_exception_handler(TableConflictError, tables.handle_table_conflict)
    app.add_exception_handler(TableOptionError, tables.handle_table_option)

    return app


app = create_app()
