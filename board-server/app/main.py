# board-server/app/main.py

"""
게시판 서버의 시작점. 앱을 만들고 라우터를 붙인다.

게시판 서버는 공지사항, 이벤트, 유저끼리의 소통, 시나리오 이야기를 맡는다.
NestJS 로 쓰던 것을 FastAPI 로 다시 썼다(#785).
주소, 요청, 응답, 오류의 모양, DB(board 스키마)는 그때와 같다. 계약 시험(contract/)이 둘 다에 같은 시나리오를 돌렸다.

  - 상태 확인(/health, /health/ready)은 API 주소 밖이다
  - 게시판과 글, 댓글, 검색은 로그인 없이 읽는다. 쓰기와 신고는 로그인, 신고의 처리와 고정은 운영자(토큰의 roles)다
  - 댓글과 답글을 알림 서버에 넣는다(#385, 발송함을 뒤에서 보낸다)
  - 인증 서버가 탈퇴를 알리는 주소(/service/users/...)는 인증 서버의 서명을 본다

띄우는 법: uv run python -m app (HOST, PORT 를 설정에서 읽는다)
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from server_core.auth import revocations
from server_core.auth.jwks import JwksCache
from server_core.database import create_engine, create_session_factory
from server_core.notifications import dispatcher
from server_core.notifications.setup import build_notifications
from server_core.notifications.store import SqlOutboxStore
from server_core.observability.db_spans import instrument_engine
from server_core.observability.http_spans import traced_client
from server_core.observability.metrics import configure_metrics, shutdown_metrics, watch_pool
from server_core.observability.middleware import RequestLoggingMiddleware
from server_core.observability.pool_metrics import pool_stats
from server_core.observability.request_metrics import RequestMetricsMiddleware
from server_core.observability.request_spans import RequestSpanMiddleware
from server_core.observability.responses import handle_unexpected_error
from server_core.observability.setup import configure_logging
from server_core.observability.tracing import FASTAPI_TELEMETRY, build_resource, configure_tracing, shutdown_tracing
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import health, me, readiness
from app.authors.service import RecentNicknames
from app.boards import router as boards
from app.comments import router as comments
from app.core.config import Settings, get_settings
from app.core.errors import use_error_bodies
from app.notifications import outbox
from app.notifications.models import OutgoingNotification
from app.posts import router as posts
from app.reports import router as reports
from app.withdrawal import router as withdrawal

# 이 서버의 API 가 놓이는 주소. 다른 서버처럼 /api/v1/<서버 이름> 이다
API_PREFIX = '/api/v1/board'


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    서버가 뜰 때와 꺼질 때 할 일. yield 앞이 뜰 때, 뒤가 꺼질 때다.

    뜰 때 끊긴 세션의 목록 받기(30초마다)와 알림 보내기(5초마다)를 시작한다. 꺼질 때 그것들을 가장 먼저 멈추고,
    DB 연결과 인증 서버로 가는 연결을 닫는다. 마지막으로 모아 둔 span 과 메트릭을 보낸다.
    """
    revoking = revocations.start(app.state.revocations)
    dispatching = dispatcher.start(app.state.notification_dispatcher)
    yield
    await dispatching.halt()
    await revoking.halt()
    await app.state.engine.dispose()
    await app.state.http_client.aclose()
    await asyncio.to_thread(shutdown_tracing, app.state.tracing)
    await asyncio.to_thread(shutdown_metrics, app.state.metrics)


def create_app(
    settings: Settings | None = None, http_client: httpx.AsyncClient | None = None, engine: AsyncEngine | None = None
) -> FastAPI:
    """
    FastAPI 앱을 만들어 돌려준다.

    http_client 는 인증 서버와 알림 서버를 부를 때 쓰는 클라이언트다. 테스트가 가짜 인증 서버로 가는 것을 넣는다.
    engine 은 DB 연결의 풀이다. 주지 않으면 설정으로 새로 만든다. 테스트는 풀 하나를 모든 앱이 함께 쓴다.
    """
    settings = settings or get_settings()

    # 로그를 공통 규격의 JSON 으로 건다(docs/observability.md). 보낼 곳이 있으면 span 과 메트릭을 수집기에 민다
    configure_logging(settings)
    resource = build_resource(settings)
    tracing = configure_tracing(settings, resource)
    metrics = configure_metrics(settings, resource)

    app = FastAPI(
        title='AI TRPG 게시판 서버',
        # API 문서 화면은 개발할 때만 연다. 운영 서버에서는 API 의 구조를 내보이지 않는다
        docs_url=f'{API_PREFIX}/docs' if settings.debug else None,
        redoc_url=None,
        openapi_url=f'{API_PREFIX}/openapi.json' if settings.debug else None,
        lifespan=lifespan,
        telemetry=FASTAPI_TELEMETRY,
    )

    # 요청의 식별자와 로그, 서버 span, HTTP 메트릭. 나중에 붙인 것이 바깥이다(다른 서버들과 같은 차례)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestSpanMiddleware)
    app.add_middleware(RequestMetricsMiddleware)

    app.state.settings = settings
    app.state.tracing = tracing
    app.state.metrics = metrics

    # DB. 엔진을 만드는 것만으로는 연결하지 않는다. DB 가 꺼져 있어도 서버는 뜬다(/health/ready 가 503 이다)
    app.state.engine = engine or create_engine(settings)
    instrument_engine(app.state.engine)
    watch_pool(pool_stats(app.state.engine, settings.db_max_connections))
    app.state.session_factory = create_session_factory(app.state.engine)

    # 인증 서버의 공개키와 끊긴 세션의 목록. 공개키는 처음 필요할 때 가져온다. 인증 서버가 죽어 있어도 뜬다
    app.state.http_client = http_client or traced_client()
    app.state.jwks = JwksCache(app.state.http_client, settings.auth_jwks_url)
    app.state.revocations = revocations.RevocationList(app.state.http_client, settings.session_revocations_url)

    # 최근에 적은 글쓴이의 닉네임(app/authors/service.py). 같은 사람의 요청마다 DB 에 쓰지 않는다
    app.state.recent_nicknames = RecentNicknames()

    # 댓글과 답글의 알림을 넣는 알림 서버. 주소(NOTIFICATION_URL)가 비면 None 이고 발송함에 적히기만 한다
    app.state.notifications = build_notifications(settings, app.state.http_client, outbox.SOURCE)
    app.state.notification_dispatcher = dispatcher.NotificationDispatcher(
        store=SqlOutboxStore(app.state.session_factory, OutgoingNotification),
        notifications=lambda: app.state.notifications,
    )

    # 상태를 확인하는 주소는 API 주소 밖에 둔다
    app.include_router(health.router)
    app.include_router(readiness.router)

    app.include_router(me.router, prefix=API_PREFIX)
    app.include_router(boards.router, prefix=API_PREFIX)
    app.include_router(posts.router, prefix=API_PREFIX)
    app.include_router(comments.router, prefix=API_PREFIX)
    app.include_router(reports.router, prefix=API_PREFIX)
    # 인증 서버가 탈퇴를 알리는 주소. 인증 서버의 서명만 본다. 프록시가 바깥에 열지 않는다
    app.include_router(withdrawal.router, prefix=API_PREFIX)

    # 거절은 {"detail"}, 입력 오류는 {"detail", "errors"} 의 400 이다(app/core/errors.py)
    use_error_bodies(app)

    # 처리하지 못한 예외는 내부를 드러내지 않는 500 으로 바꾼다. 원인은 로그에 남긴다
    app.add_exception_handler(Exception, handle_unexpected_error)

    return app


# uvicorn 이 찾는 앱. 테스트는 이것을 쓰지 않고 create_app 으로 따로 만든다
app = create_app()
