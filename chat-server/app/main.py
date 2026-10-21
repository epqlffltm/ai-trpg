# chat-server/app/main.py

"""
chat 서버의 시작점. 앱을 만들고 라우터를 붙인다.

chat 서버는 캐릭터 하나와의 1:1 대화를 맡는다(docs/architecture/chat-server.md). story 는 story-server 가 맡는다.
상태 확인, 토큰의 주인, 대화(캐릭터의 판과 페르소나를 asset 서버에서 가져와 시작하기, 목록, 읽기, 지우기)가 있다.
한 번의 말(스트리밍, 과금)이 다음으로 붙는다.

띄우는 법: uv run uvicorn app.main:app --port 8005 --reload
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from server_core.auth import revocations
from server_core.auth.jwks import JwksCache
from server_core.database import create_engine, create_session_factory
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
from app.assets.client import AssetClient, AssetUnavailableError
from app.conversations import router as conversations
from app.conversations.service import (
    AdultContentRequiredError,
    CharacterNotFoundError,
    ConversationNotFoundError,
    PersonaNotFoundError,
    StartNotFoundError,
)
from app.core.config import Settings, get_settings

# 이 서버의 API 가 놓이는 주소. 다른 서버처럼 /api/v1/<서버 이름> 이다(인증 /api/v1/auth, 게임 /api/v1/game)
API_PREFIX = '/api/v1/chat'


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    서버가 뜰 때와 꺼질 때 할 일. yield 앞이 뜰 때, 뒤가 꺼질 때다.

    뜰 때 끊긴 세션의 목록 받기(30초마다)를 시작한다. 꺼질 때 그것을 가장 먼저 멈추고,
    DB 연결과 인증 서버로 가는 연결을 닫는다. 닫지 않으면 상대 쪽에 끊긴 연결이 한동안 남는다.
    마지막으로 모아 둔 span 과 메트릭을 보낸다. 보내기를 기다리느라 막히므로 스레드에서 한다.
    """
    revoking = revocations.start(app.state.revocations)
    yield
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

    모듈을 불러올 때 바로 만들지 않고 함수로 둔다. 테스트가 설정을 바꿔 가며 앱을 여러 개 만들 수 있다.
    http_client 는 인증 서버에 요청을 보낼 때 쓰는 클라이언트다. 테스트가 가짜 인증 서버로 가는 것을 넣는다.
    engine 은 DB 연결의 풀이다. 주지 않으면 설정으로 새로 만든다.
    테스트는 풀 하나를 만들어 모든 앱이 함께 쓴다. 테스트마다 새 연결을 맺지 않는다.
    """
    settings = settings or get_settings()

    # 로그를 공통 규격의 JSON 으로 건다(docs/observability.md). 여러 번 불러도 처리기는 하나다
    configure_logging(settings)
    # 보낼 곳(OTEL_EXPORTER_OTLP_ENDPOINT)이 있으면 span 과 메트릭을 수집기에 민다. 없으면 None 이고 나가는 것이 없다.
    # 둘이 같은 출처(같은 service.instance.id)를 쓴다
    resource = build_resource(settings)
    tracing = configure_tracing(settings, resource)
    metrics = configure_metrics(settings, resource)

    app = FastAPI(
        title='AI TRPG chat 서버',
        # API 문서 화면은 개발할 때만 연다. 운영 서버에서는 API 의 구조를 내보이지 않는다
        docs_url=f'{API_PREFIX}/docs' if settings.debug else None,
        redoc_url=None,
        openapi_url=f'{API_PREFIX}/openapi.json' if settings.debug else None,
        lifespan=lifespan,
        # FastAPI 가 스스로 span, 메트릭, 로그를 내보내지 않게 한다(server_core/observability/tracing.py)
        telemetry=FASTAPI_TELEMETRY,
    )

    # 요청마다 식별자(request_id, trace_id)를 걸고, 끝나면 한 줄을 남긴다. 응답에 X-Request-ID 를 돌려준다
    app.add_middleware(RequestLoggingMiddleware)
    # 요청마다 서버 span 을 건다. 나중에 붙인 것이 바깥이다. 로그(trace_id)와 쿼리의 span 이 이 span 을 따른다
    app.add_middleware(RequestSpanMiddleware)
    # 요청마다 HTTP 메트릭 셋을 센다. 맨 바깥이라 요청 전체(span 과 로그를 거는 시간까지)를 잰다
    app.add_middleware(RequestMetricsMiddleware)

    # 요청을 처리하는 코드가 설정을 꺼내 쓸 수 있게 앱에 붙여 둔다. 전역 변수로 두지 않는다
    app.state.settings = settings
    app.state.tracing = tracing
    app.state.metrics = metrics

    # 엔진과 세션 틀을 앱에 붙여 둔다. 앱마다 자기 엔진을 가지므로 테스트끼리 섞이지 않는다.
    # 엔진을 만드는 것만으로는 DB 에 연결하지 않는다. DB 가 꺼져 있어도 서버는 뜬다(/health/ready 가 503 이다)
    app.state.engine = engine or create_engine(settings)
    # 쿼리마다 span 을 건다(요청이나 작업 안의 것만). 같은 엔진에 여러 번 불러도 한 번만 단다
    instrument_engine(app.state.engine)
    watch_pool(pool_stats(app.state.engine, settings.db_max_connections))
    app.state.session_factory = create_session_factory(app.state.engine)

    # 인증 서버의 공개키(server_core/auth/jwks.py)와 끊긴 세션의 목록(server_core/auth/revocations.py).
    # 공개키는 처음 필요할 때 가져온다. 인증 서버가 죽어 있어도 이 서버는 뜬다.
    # 요청 안에서 부르면 client span 을 걸고 traceparent 를 그 span 으로 잇는다(인증 서버는 우리 서버다)
    app.state.http_client = http_client or traced_client()
    app.state.jwks = JwksCache(app.state.http_client, settings.auth_jwks_url)
    app.state.revocations = revocations.RevocationList(app.state.http_client, settings.session_revocations_url)
    # asset 서버를 부르는 것(app/assets/client.py). 같은 연결의 풀을 쓴다. 요청 안에서 부르면 client span 이 걸린다
    app.state.asset = AssetClient(
        app.state.http_client,
        settings.asset_url,
        settings.asset_secret.get_secret_value(),
        settings.asset_timeout_seconds,
    )

    # 상태를 확인하는 주소는 API 주소 밖에 둔다. 프록시와 관리 도구가 부르는 것이라 버전이 없다
    app.include_router(health.router)
    app.include_router(readiness.router)

    # 토큰의 주인을 돌려주는 주소. 인증 서버의 access 토큰(대상 ai-trpg-chat)으로 확인한다
    app.include_router(me.router, prefix=API_PREFIX)
    # 대화. 캐릭터의 판과 페르소나를 asset 서버에서 가져와 시작한다
    app.include_router(conversations.router, prefix=API_PREFIX)

    app.add_exception_handler(ConversationNotFoundError, conversations.handle_conversation_not_found)
    app.add_exception_handler(CharacterNotFoundError, conversations.handle_character_not_found)
    app.add_exception_handler(PersonaNotFoundError, conversations.handle_persona_not_found)
    app.add_exception_handler(AdultContentRequiredError, conversations.handle_adult_content_required)
    app.add_exception_handler(StartNotFoundError, conversations.handle_start_not_found)
    app.add_exception_handler(AssetUnavailableError, conversations.handle_asset_unavailable)

    # 처리하지 못한 예외는 내부를 드러내지 않는 500 으로 바꾼다.
    # 원인은 로그에 남긴다(server_core/observability/responses.py)
    app.add_exception_handler(Exception, handle_unexpected_error)

    return app


# uvicorn 이 찾는 앱. 테스트는 이것을 쓰지 않고 create_app 으로 따로 만든다
app = create_app()
