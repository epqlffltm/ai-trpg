# game-server/app/main.py

"""
게임 서버의 시작점. FastAPI 앱을 만들고 라우터를 붙인다.

    uv run uvicorn app.main:app --port 8001 --reload --timeout-graceful-shutdown 5
"""

import asyncio
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
from app.chat import router as chat
from app.chat.typing import TypingThrottle
from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory
from app.core.jobs import BackgroundJobs
from app.engine.dice import RandomDice
from app.events import router as events
from app.listings import router as listings
from app.listings.service import ListingNotReadyError
from app.lore.indexing import LoreIndexer
from app.lore.retrieval import LoreRetriever, Thresholds
from app.lore.setup import build_embedder
from app.memory.history import HistoryCollector
from app.memory.indexing import MemoryIndexer
from app.memory.retrieval import MemoryRetriever, MemoryThresholds
from app.personas import router as personas
from app.personas.service import PersonaConflictError, PersonaNotFoundError
from app.realtime import router as realtime
from app.realtime.hub import Hub
from app.realtime.listener import PostgresListener
from app.realtime.shutdown import closing_on_exit
from app.rounds import router as rounds
from app.rounds.narrator_setup import build_narrator
from app.rounds.service import ActionNotInRulesError, ActionTargetError, RoundConflictError, RoundNotFoundError
from app.tables import router as tables
from app.tables.service import (
    MemberNotFoundError,
    NotHostError,
    TableConflictError,
    TableNotFoundError,
    TableOptionError,
    WrongPasswordError,
)

# 이 서버의 API 가 놓이는 주소. 인증 서버는 /api/v1/auth 를 쓴다
API_PREFIX = '/api/v1/game'


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    서버가 뜰 때와 꺼질 때 할 일. yield 앞이 뜰 때, 뒤가 꺼질 때다.

    떠 있는 동안 종료 신호가 오면 방송실부터 닫는다. 열린 스트림이 끝나야 서버가 yield 뒤로 넘어온다
    (app/realtime/shutdown.py). 닫는 일은 신호 처리기가 아니라 이벤트 루프가 한다.
    꺼질 때 신호를 듣는 연결, DB 연결, 인증 서버로 가는 연결을 전부 닫는다.
    닫지 않으면 상대 쪽에 끊긴 연결이 한동안 남는다.
    """
    loop = asyncio.get_running_loop()
    with closing_on_exit(lambda: loop.call_soon_threadsafe(app.state.hub.close_all)):
        yield
    # 뒤에서 돌던 작업을 먼저 마무리한다. 작업이 DB 를 쓰므로 DB 를 닫기 전에 한다
    await app.state.jobs.aclose()
    await app.state.signal_source.stop()
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

    # 스트림을 열어 둔 연결들을 깨우는 방송실과, 다른 요청(다른 서버)이 보낸 신호를 듣는 것.
    # 만드는 것만으로는 DB 에 연결하지 않는다. 처음 스트림이 열릴 때 연결한다.
    # 신호를 다른 것으로 바꿀 때 여기의 PostgresListener 를 바꿔 끼운다(app/realtime/listener.py)
    app.state.hub = Hub()
    app.state.signal_source = PostgresListener(settings, app.state.hub)

    # "입력 중" 신호를 너무 자주 보내지 못하게 막는 것. 기록을 메모리에 두므로 앱에 하나만 둔다
    app.state.typing_throttle = TypingThrottle()

    # 요청과 따로 도는 작업을 들고 있는 것. GM 의 서술이 여기서 돈다(app/rounds/closing.py)
    app.state.jobs = BackgroundJobs()

    # 판정에 쓰는 주사위. 서버만 굴린다. 테스트는 정해진 눈을 내는 주사위로 바꿔 꽂는다
    app.state.dice = RandomDice()

    # GM 의 서술을 만드는 것. 설정(NARRATOR)이 정한다. 기본은 AI 를 부르지 않는 가짜다.
    # 언어 모델이면 위의 httpx 클라이언트로 부른다. 앱이 꺼질 때 그 클라이언트를 닫는다.
    # 부를 때마다 위의 세션 틀로 DB 에 기록을 남긴다(app/ai/call_log.py)
    app.state.narrator = build_narrator(settings, app.state.http_client, app.state.session_factory)

    # 로어북 항목을 벡터로 바꾸는 것. 설정(EMBEDDER)이 정한다. 기본은 모델을 부르지 않는 가짜다.
    # 시나리오를 게시하면 뒤에서 판의 항목을 벡터로 바꾼다(app/lore/indexing.py)
    app.state.embedder = build_embedder(settings, app.state.http_client)

    # 서술하기 직전에 이번 장면에 맞는 로어북 항목을 고르는 것(app/lore/retrieval.py).
    # 판의 벡터가 모자라면 위의 임베더로 색인을 다시 맡긴다.
    # 거리 기준은 설정(LORE_MAX_DISTANCE, LORE_KEYWORD_MAX_DISTANCE)이 정한다
    indexer = LoreIndexer(app.state.session_factory, app.state.embedder, app.state.jobs)
    thresholds = Thresholds(settings.lore_max_distance, settings.lore_keyword_max_distance)
    app.state.lore = LoreRetriever(app.state.session_factory, app.state.embedder, indexer, thresholds)

    # 서술하기 직전에 지난 기록보다 앞의 라운드 중 이번 장면에 맞는 것을 고르는 것(app/memory/retrieval.py).
    # 테이블의 라운드 벡터가 모자라면 위의 임베더로 색인을 맡긴다.
    # 거리 기준은 설정(MEMORY_MAX_DISTANCE, MEMORY_KEYWORD_MAX_DISTANCE)이 정한다
    memory_indexer = MemoryIndexer(app.state.session_factory, app.state.embedder, app.state.jobs)
    memory_thresholds = MemoryThresholds(settings.memory_max_distance, settings.memory_keyword_max_distance)
    app.state.memories = MemoryRetriever(
        app.state.session_factory, app.state.embedder, memory_indexer, memory_thresholds
    )

    # 로어북이 고른 인물마다 지난 서술에서 그 인물이 나온 문장을 모으는 것(app/memory/history.py). 모델을 부르지 않는다
    app.state.histories = HistoryCollector(app.state.session_factory)

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
    app.include_router(personas.router, prefix=API_PREFIX)
    app.include_router(tables.router, prefix=API_PREFIX)
    app.include_router(rounds.router, prefix=API_PREFIX)
    app.include_router(events.router, prefix=API_PREFIX)
    app.include_router(chat.router, prefix=API_PREFIX)
    app.include_router(realtime.router, prefix=API_PREFIX)

    # 서비스가 던지는 예외를 HTTP 응답으로 바꾸는 곳. API 함수마다 try 를 쓰지 않는다
    app.add_exception_handler(AssetNotFoundError, handle_asset_not_found)
    app.add_exception_handler(AssetInUseError, handle_asset_in_use)
    app.add_exception_handler(AssetReferenceError, handle_asset_reference)
    app.add_exception_handler(LorebookFullError, lorebooks.handle_lorebook_full)
    app.add_exception_handler(ScenarioNotReadyError, scenarios.handle_scenario_not_ready)
    app.add_exception_handler(ListingNotReadyError, listings.handle_listing_not_ready)
    app.add_exception_handler(PersonaNotFoundError, personas.handle_persona_not_found)
    app.add_exception_handler(PersonaConflictError, personas.handle_persona_conflict)
    app.add_exception_handler(TableNotFoundError, tables.handle_table_not_found)
    app.add_exception_handler(MemberNotFoundError, tables.handle_member_not_found)
    app.add_exception_handler(NotHostError, tables.handle_not_host)
    app.add_exception_handler(WrongPasswordError, tables.handle_wrong_password)
    app.add_exception_handler(TableConflictError, tables.handle_table_conflict)
    app.add_exception_handler(TableOptionError, tables.handle_table_option)
    app.add_exception_handler(RoundNotFoundError, rounds.handle_round_not_found)
    app.add_exception_handler(RoundConflictError, rounds.handle_round_conflict)
    app.add_exception_handler(ActionNotInRulesError, rounds.handle_action_not_in_rules)
    app.add_exception_handler(ActionTargetError, rounds.handle_action_target)

    return app


app = create_app()
