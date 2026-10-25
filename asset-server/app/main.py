# asset-server/app/main.py

"""
asset 서버의 시작점. 앱을 만들고 라우터를 붙인다.

asset 서버는 캐릭터, 계정 페르소나, 그림의 원본을 맡는다(docs/architecture/asset-server.md).
상태 확인, 토큰의 주인, 계정 페르소나(#565), 캐릭터와 게시와 공개 목록(#567), 그림 올리기와 내주기(#566)가 있다.
다른 서버(chat)가 페르소나의 사본과 판을 가져가는 주소(/service/{caller}/...)는
그 서버의 서명과 사용자의 토큰을 함께 본다.
인증 서버가 탈퇴를 알리는 주소(/service/users/...)는 인증 서버의 서명을 본다.
운영자의 숨김과 신고 처리를 알림 서버에 넣는다(#678, 발송함을 뒤에서 보낸다).

띄우는 법: uv run uvicorn app.main:app --port 8006 --reload
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from server_core.auth import revocations
from server_core.auth.jwks import JwksCache
from server_core.database import create_engine, create_session_factory
from server_core.input_errors import use_input_errors
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
from app.characters import listings as character_listings
from app.characters import router as characters
from app.characters import supply as character_supply
from app.characters.publishing import CharacterNotReadyError
from app.characters.service import CharacterNotFoundError, LorebookNotOwnedError, OperatorOnlyError
from app.core.config import Settings, get_settings
from app.images import router as images
from app.images.isolation import ImageUnreadableError
from app.images.service import ImageNotFoundError, ImageNotOwnedError, UnsupportedImageError
from app.images.setup import build_decoder, build_image_store
from app.images.store import ImageStoreUnavailableError
from app.lorebooks import router as lorebooks
from app.lorebooks.service import LorebookNotFoundError
from app.notifications import outbox
from app.notifications.models import OutgoingNotification
from app.operators import router as operators
from app.personas import router as personas
from app.personas import supply as persona_supply
from app.personas.service import PersonaLimitError, PersonaNotFoundError
from app.ratings import AdultContentRequiredError, handle_adult_content_required
from app.reports import router as reports
from app.reports.service import AlreadyReportedError, OwnCharacterReportError
from app.withdrawal import router as withdrawal
from app.worlds import router as worlds
from app.worlds import supply as world_supply
from app.worlds.publishing import WorldNotReadyError
from app.worlds.service import CharacterNotOwnedError, WorldNotFoundError

# 이 서버의 API 가 놓이는 주소. 다른 서버처럼 /api/v1/<서버 이름> 이다(인증 /api/v1/auth, 게임 /api/v1/game)
API_PREFIX = '/api/v1/asset'


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    서버가 뜰 때와 꺼질 때 할 일. yield 앞이 뜰 때, 뒤가 꺼질 때다.

    뜰 때 끊긴 세션의 목록 받기(30초마다)와 알림 보내기(5초마다)를 시작한다. 꺼질 때 그것들을 가장 먼저 멈추고,
    DB 연결과 인증 서버로 가는 연결을 닫는다. 닫지 않으면 상대 쪽에 끊긴 연결이 한동안 남는다.
    마지막으로 모아 둔 span 과 메트릭을 보낸다. 보내기를 기다리느라 막히므로 스레드에서 한다.
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
        title='AI TRPG asset 서버',
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
    # 그림 저장소와 그림을 여는 따로 된 프로세스(#566). 저장소도 같은 클라이언트로 부른다(client span 이 걸린다)
    app.state.image_store = build_image_store(settings, app.state.http_client)
    app.state.image_decoder = build_decoder(settings)
    # 운영자의 숨김과 신고 처리를 넣는 알림 서버(#678). 설정(NOTIFICATION_URL)이 정한다. 비우면 None 이고
    # 알림은 발송함에 적히기만 한다. 같은 클라이언트로 부른다(client span 과 traceparent 가 걸린다)
    app.state.notifications = build_notifications(settings, app.state.http_client, outbox.SOURCE)
    # 발송함의 알림을 몇 초마다 알림 서버에 보내는 작업(server_core/notifications/dispatcher.py).
    # lifespan 이 돌리고 멈춘다.
    # 알림 서버를 부르는 것은 부를 때마다 앱에서 꺼낸다. 테스트가 가짜를 꽂는다
    app.state.notification_dispatcher = dispatcher.NotificationDispatcher(
        store=SqlOutboxStore(app.state.session_factory, OutgoingNotification),
        notifications=lambda: app.state.notifications,
    )

    # 상태를 확인하는 주소는 API 주소 밖에 둔다. 프록시와 관리 도구가 부르는 것이라 버전이 없다
    app.include_router(health.router)
    app.include_router(readiness.router)

    # 토큰의 주인을 돌려주는 주소. 인증 서버의 access 토큰(대상 ai-trpg-asset)으로 확인한다
    app.include_router(me.router, prefix=API_PREFIX)
    # 계정 페르소나(#565). 주인만 다룬다
    app.include_router(personas.router, prefix=API_PREFIX)

    app.add_exception_handler(PersonaNotFoundError, personas.handle_persona_not_found)
    app.add_exception_handler(PersonaLimitError, personas.handle_persona_limit)
    # 캐릭터의 초안과 판(#567), 공개 목록. 공개 목록은 로그인하지 않아도 읽는다
    app.include_router(characters.router, prefix=API_PREFIX)
    app.include_router(character_listings.router, prefix=API_PREFIX)

    app.add_exception_handler(CharacterNotFoundError, characters.handle_character_not_found)
    app.add_exception_handler(OperatorOnlyError, characters.handle_operator_only)
    app.add_exception_handler(CharacterNotReadyError, characters.handle_character_not_ready)
    app.add_exception_handler(LorebookNotOwnedError, characters.handle_lorebook_not_owned)
    app.add_exception_handler(AdultContentRequiredError, handle_adult_content_required)
    # 그림(#566). 올리기는 로그인, 내주기는 볼 수 있는지 보고 nginx 에 넘긴다
    app.include_router(reports.router, prefix=API_PREFIX)
    app.add_exception_handler(OwnCharacterReportError, reports.handle_own_character)
    app.add_exception_handler(AlreadyReportedError, reports.handle_already_reported)
    app.include_router(operators.router, prefix=API_PREFIX)

    app.include_router(lorebooks.router, prefix=API_PREFIX)
    app.add_exception_handler(LorebookNotFoundError, lorebooks.handle_lorebook_not_found)
    # story 의 세계관의 초안과 판(#591, 화면 명세 D7). 만든 사람만 다룬다
    app.include_router(worlds.router, prefix=API_PREFIX)
    app.add_exception_handler(WorldNotFoundError, worlds.handle_world_not_found)
    app.add_exception_handler(WorldNotReadyError, worlds.handle_world_not_ready)
    app.add_exception_handler(CharacterNotOwnedError, worlds.handle_character_not_owned)

    app.include_router(images.router, prefix=API_PREFIX)

    app.add_exception_handler(UnsupportedImageError, images.handle_unsupported_image)
    app.add_exception_handler(ImageUnreadableError, images.handle_unreadable_image)
    app.add_exception_handler(ImageNotFoundError, images.handle_image_not_found)
    app.add_exception_handler(ImageNotOwnedError, images.handle_image_not_owned)
    app.add_exception_handler(ImageStoreUnavailableError, images.handle_store_unavailable)
    # 다른 서버가 페르소나의 사본과 판을 가져가는 주소.
    # 그 서버의 서명(app/core/service_auth.py)과 사용자의 토큰을 함께 본다.
    # 프록시가 바깥에 열지 않는다(docker/nginx/templates/api.inc.template)
    app.include_router(persona_supply.router, prefix=API_PREFIX)
    app.include_router(character_supply.router, prefix=API_PREFIX)
    app.include_router(world_supply.router, prefix=API_PREFIX)
    # 인증 서버가 탈퇴를 알리는 주소(docs/architecture/withdrawal.md). 인증 서버의 서명만 본다
    app.include_router(withdrawal.router, prefix=API_PREFIX)

    # 칸이 틀린 요청은 서버들이 함께 쓰는 본문 {"detail", "errors"} 의 422 로 답한다(server_core/input_errors.py)
    use_input_errors(app)

    # 처리하지 못한 예외는 내부를 드러내지 않는 500 으로 바꾼다.
    # 원인은 로그에 남긴다(server_core/observability/responses.py)
    app.add_exception_handler(Exception, handle_unexpected_error)

    return app


# uvicorn 이 찾는 앱. 테스트는 이것을 쓰지 않고 create_app 으로 따로 만든다
app = create_app()
