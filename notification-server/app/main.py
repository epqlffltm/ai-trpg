# notification-server/app/main.py

"""
알림 서버의 시작점. 앱을 만들고 라우터를 붙인다.

띄우는 법: uv run uvicorn app.main:app --port 8004 --reload
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import health, readiness
from app.auth import revocations
from app.auth.jwks import JwksCache
from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory
from app.inbox import router as inbox
from app.notifications import retention
from app.notifications import router as notifications
from app.observability.middleware import RequestLoggingMiddleware
from app.observability.responses import handle_unexpected_error
from app.observability.setup import configure_logging

# 이 서버의 API 가 놓이는 주소. 다른 서버처럼 /api/v1/<서버 이름> 이다(인증 /api/v1/auth, 게임 /api/v1/game)
API_PREFIX = '/api/v1/notification'


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    서버가 뜰 때와 꺼질 때 할 일. yield 앞이 뜰 때, 뒤가 꺼질 때다.

    뜰 때 끊긴 세션의 목록 받기(30초마다)와 보관 기간이 지난 알림 지우기(한 시간마다)를 시작한다.
    꺼질 때 그 둘을 가장 먼저 멈추고,
    DB 연결과 인증 서버로 가는 연결을 닫는다. 닫지 않으면 상대 쪽에 끊긴 연결이 한동안 남는다.
    """
    revoking = revocations.start(app.state.revocations)
    pruning = retention.start(app.state.notification_pruner)
    yield
    await pruning.halt()
    await revoking.halt()
    await app.state.engine.dispose()
    await app.state.http_client.aclose()


def create_app(
    settings: Settings | None = None, http_client: httpx.AsyncClient | None = None, engine: AsyncEngine | None = None
) -> FastAPI:
    """
    FastAPI 앱을 만들어 돌려준다.

    모듈을 불러올 때 바로 만들지 않고 함수로 둔다. 테스트가 설정을 바꿔 가며 앱을 여러 개 만들 수 있다.
    http_client 는 인증 서버에 요청을 보낼 때 쓰는 클라이언트다. 테스트가 가짜 인증 서버로 가는 것을 넣는다.
    engine 은 DB 연결의 풀이다. 주지 않으면 설정으로 새로 만든다.
    테스트는 풀 하나를 만들어 모든 앱이 함께 쓴다. 테스트마다 새 연결을 맺지 않는다.
    """
    settings = settings or get_settings()

    # 로그를 공통 규격의 JSON 으로 건다(docs/observability.md). 여러 번 불러도 처리기는 하나다
    configure_logging(settings)

    app = FastAPI(
        title='AI TRPG 알림 서버',
        # API 문서 화면은 개발할 때만 연다. 운영 서버에서는 API 의 구조를 내보이지 않는다
        docs_url=f'{API_PREFIX}/docs' if settings.debug else None,
        redoc_url=None,
        openapi_url=f'{API_PREFIX}/openapi.json' if settings.debug else None,
        lifespan=lifespan,
    )

    # 요청마다 식별자(request_id, trace_id)를 걸고, 끝나면 한 줄을 남긴다. 응답에 X-Request-ID 를 돌려준다
    app.add_middleware(RequestLoggingMiddleware)

    # 요청을 처리하는 코드가 설정을 꺼내 쓸 수 있게 앱에 붙여 둔다. 전역 변수로 두지 않는다
    app.state.settings = settings

    # 엔진과 세션 틀을 앱에 붙여 둔다. 앱마다 자기 엔진을 가지므로 테스트끼리 섞이지 않는다.
    # 엔진을 만드는 것만으로는 DB 에 연결하지 않는다. DB 가 꺼져 있어도 서버는 뜬다(/health/ready 가 503 이다)
    app.state.engine = engine or create_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)

    # 인증 서버의 공개키(app/auth/jwks.py)와 끊긴 세션의 목록(app/auth/revocations.py).
    # 공개키는 처음 필요할 때 가져온다. 인증 서버가 죽어 있어도 이 서버는 뜬다
    app.state.http_client = http_client or httpx.AsyncClient()
    app.state.jwks = JwksCache(app.state.http_client, settings.auth_jwks_url)
    app.state.revocations = revocations.RevocationList(app.state.http_client, settings.session_revocations_url)

    # 보관 기간이 지난 알림을 지우는 정리 작업. lifespan 이 돌리고 멈춘다
    app.state.notification_pruner = retention.NotificationPruner(
        session_factory=app.state.session_factory,
        retention_days=settings.notification_retention_days,
    )

    # 상태를 확인하는 주소는 API 주소 밖에 둔다. 프록시와 관리 도구가 부르는 것이라 버전이 없다
    app.include_router(health.router)
    app.include_router(readiness.router)

    # 다른 서버가 알림을 넣는 주소. 사용자의 토큰이 아니라 그 서버의 서명으로 확인한다
    app.include_router(notifications.router, prefix=API_PREFIX)
    # 사용자가 자기 알림함을 읽는 주소. 인증 서버의 access 토큰으로 확인한다
    app.include_router(inbox.router, prefix=API_PREFIX)

    # 처리하지 못한 예외는 내부를 드러내지 않는 500 으로 바꾼다. 원인은 로그에 남긴다(app/observability/responses.py)
    app.add_exception_handler(Exception, handle_unexpected_error)

    return app


# uvicorn 이 찾는 앱. 테스트는 이것을 쓰지 않고 create_app 으로 따로 만든다
app = create_app()
