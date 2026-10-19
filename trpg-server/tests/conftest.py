# trpg-server/tests/conftest.py

"""
테스트가 함께 쓰는 준비물.

pytest 는 이 파일의 fixture 를 모든 테스트 파일에서 이름만으로 쓸 수 있게 해 준다.

테스트는 실제 PostgreSQL 에서 돈다. 개발용과 같은 DB 를 쓰되 스키마를 나눈다.
개발용 데이터는 game 스키마에, 테스트는 game_test 스키마에 있다.
"""

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.database import create_engine
from app.limits.setup import Limiting, build_limiting
from app.main import create_app
from app.realtime import service as stream_service
from app.realtime.service import Cursor
from tests.cleaning import clear_tables
from tests.narration_model import add_test_model
from tests.signing import FakeAuthServer, SigningKey, make_signing_key, make_viewer
from tests.spans import SpanRecorder, recording
from tests.streaming import LONG_HEARTBEAT, Reader

TEST_SCHEMA = 'game_test'

# 존재하지 않는 주소. 테스트는 실제 인증 서버에 요청을 보내지 않는다
TEST_JWKS_URL = 'http://auth.test/api/v1/auth/jwks'


def make_test_settings(**overrides) -> Settings:
    """
    테스트용 설정을 만든다.

    DB 주소는 개발 환경의 것(.env 또는 환경 변수)을 그대로 읽는다. 비밀번호를 테스트 코드에 적지 않는다.
    동작을 바꾸는 값은 여기서 고정한다. 개발자의 .env 에 무엇이 적혀 있든 테스트 결과가 같아야 한다.
    """
    # narrator 와 embedder 는 가짜로 고정한다. 개발자의 .env 가 모델을 켜 두었어도 테스트가 실제 모델을 부르지 않는다.
    # 로어북 검색의 거리 기준은 가짜 임베더에 맞춘 값이다. 가짜는 낱말이 겹치는지만 보는 벡터라 거리의 크기가
    # bge-m3 와 다르다(기본값 0.45, 0.50 이면 이름이 나온 항목도 걸러진다). 키워드의 상한은 끈다(코사인 거리는 2 까지).
    # 지난 일(기억)의 거리 기준도 같은 까닭으로 가짜에 맞춘다
    # 결제 서버는 부르지 않는다(받지 않는 것). 결제 서버를 쓰는 테스트는 가짜를 꽂는다(tests/billing.py)
    # 알림 서버도 부르지 않는다(발송함에 적기만 한다).
    # 보내는 것을 보는 테스트는 가짜를 꽂는다(tests/test_notifications.py)
    # 시도 횟수 제한은 끈다. 채팅을 여러 번 쓰는 테스트가 막히지 않게 한다.
    # 제한을 보는 테스트만 켠다(tests/test_attempt_limits.py).
    # Redis 는 쓰지 않는다(메모리). Redis 로 세는 것은 그 파일이 따로 본다
    # OpenAI, Anthropic, Gemini, Z.ai 의 키와 주소도 비우고 고정한다. 개발자의 .env 에 진짜 키가 있어도
    # 테스트가 실제 API 를 부르거나 키를 쥐지 않는다
    # 로그는 경고부터 남긴다. 요청마다 한 줄씩 남는 것(info)까지 남기면, 로그를 잡아 "이 줄 하나만 남았다"를 보는
    # 테스트에 요청의 줄이 섞인다. 요청의 줄을 보는 테스트는 그 로거의 수준을 내려서 잡는다
    values = {
        'debug': False,
        'log_level': 'warning',
        'db_schema': TEST_SCHEMA,
        'auth_jwks_url': TEST_JWKS_URL,
        'narrator': 'fake',
        'embedder': 'fake',
        'lore_max_distance': 0.6,
        'lore_keyword_max_distance': 2.0,
        'memory_max_distance': 0.6,
        'memory_keyword_max_distance': 2.0,
        'billing_url': '',
        'billing_secret': '',
        'notification_url': '',
        'notification_secret': '',
        'openai_api_key': '',
        'openai_base_url': 'https://api.openai.com/v1',
        'anthropic_api_key': '',
        'anthropic_base_url': 'https://api.anthropic.com',
        'gemini_api_key': '',
        'gemini_base_url': 'https://generativelanguage.googleapis.com',
        'zai_api_key': '',
        'zai_base_url': 'https://api.z.ai/api/paas/v4',
        'redis_url': '',
        'limits_enabled': False,
        # span 을 내보내지 않는다. 개발자의 .env 에 수집기의 주소가 있어도 테스트는 보내지 않는다.
        # span 을 보는 테스트는 메모리에 모으는 것을 끼운다(spans fixture)
        'otel_exporter_otlp_endpoint': '',
    }
    values.update(overrides)
    return Settings(**values)


def no_limits() -> Limiting:
    """세지도 막지도 않는 시도 횟수 제한. 서비스를 바로 부르는 테스트가 넘긴다."""
    return build_limiting(make_test_settings(), None)


def make_client(app: FastAPI) -> AsyncClient:
    """
    앱에 요청을 보내는 클라이언트를 만든다.

    서버를 실제로 띄우지 않는다. 요청을 네트워크 없이 앱에 바로 넘긴다.
    """
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver')


@pytest.fixture
def settings() -> Settings:
    """테스트용 설정."""
    settings = make_test_settings()
    # 설정을 잘못 건드려 개발용 스키마에서 테스트가 도는 일을 막는다
    assert settings.db_schema.endswith('_test'), '테스트는 테스트용 스키마에서만 돈다'
    return settings


@pytest.fixture(scope='session')
def signing_key() -> SigningKey:
    """인증 서버의 서명 키. 만드는 데 시간이 걸려서 테스트 전체에서 한 번만 만든다."""
    return make_signing_key('test-key')


@pytest.fixture
def auth_server(signing_key: SigningKey) -> FakeAuthServer:
    """가짜 인증 서버. 테스트마다 새로 만든다. 죽이거나 키를 바꿔도 다른 테스트에 번지지 않는다."""
    return FakeAuthServer(keys=[signing_key])


@pytest.fixture(scope='session')
async def engine() -> AsyncIterator[AsyncEngine]:
    """
    DB 연결의 풀. 테스트 전체에서 하나를 만들어 모든 테스트의 앱이 함께 쓴다(#223).

    테스트마다 풀을 새로 만들면 전체 한 번에 연결을 수천 번 새로 맺는다. 연결을 맺는 데는 왕복이 여럿 든다.
    Windows 의 Docker(WSL2)는 그 왕복을 가끔 몇 초씩 붙잡아, 연결 제한 시간(5초)에 걸린 테스트가 흩어져 실패했다.
    함께 쓰면 연결을 몇 개만 맺고 다시 쓴다. 연결은 만든 이벤트 루프에 묶이므로 테스트의 루프도 하나다(pyproject.toml).
    테이블을 비우는 것(clean_tables)은 그대로라 테스트끼리 데이터가 섞이지 않는다.
    """
    shared = create_engine(make_test_settings())
    yield shared
    await shared.dispose()


@pytest.fixture
async def app(settings: Settings, auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """
    테스트용 설정으로 만든 앱. 인증 서버 자리에 가짜를 꽂는다. DB 연결의 풀은 테스트 전체의 것을 쓴다(engine).

    테스트가 끝나면 뒤의 작업을 마무리하고 연결을 닫는다. 테스트에서는 lifespan 이 돌지 않으므로 직접 닫는다.
    풀은 닫지 않는다. 다음 테스트가 쓴다. 쓰던 연결은 풀로 돌아가 있다(세션이 닫히면서 되돌린다).
    """
    app = create_app(settings, http_client=auth_server.make_client(), engine=engine)
    yield app
    await app.state.jobs.aclose()
    await app.state.signal_source.stop()
    await app.state.http_client.aclose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """테스트용 앱에 요청을 보내는 클라이언트."""
    async with make_client(app) as test_client:
        yield test_client


@pytest.fixture
async def session(app: FastAPI) -> AsyncIterator[AsyncSession]:
    """테스트가 DB 를 직접 들여다볼 때 쓰는 세션."""
    async with app.state.session_factory() as db_session:
        yield db_session


@pytest.fixture
async def clean_tables(app: FastAPI) -> None:
    """
    테이블을 비우고 테스트를 시작한다. DB 에 쓰는 테스트가 쓴다.

    테스트를 트랜잭션으로 감싸 되돌리는 방법을 쓰지 않는다.
    그러면 앱의 커밋이 진짜로 일어나지 않아, 저장의 경계가 맞는지 볼 수 없다.
    끝난 뒤가 아니라 시작할 때 비운다. 앞의 테스트가 도중에 죽어 찌꺼기를 남겨도 영향을 받지 않는다.
    비운 뒤 모델 목록에 테스트 모델 하나를 켜 둔다. 시나리오는 추천 서술 모델이 있어야 저장된다
    (tests/narration_model.py).
    """
    await clear_tables(app.state.engine)
    await add_test_model(app.state.engine)


@pytest.fixture
async def empty_catalog(app: FastAPI) -> None:
    """clean_tables 와 같되 모델 목록을 비워 둔 채 시작한다. 모델 목록 자체를 보는 테스트가 쓴다."""
    await clear_tables(app.state.engine)


@pytest.fixture
def narrated(app: FastAPI):
    """
    뒤에서 도는 서술이 끝날 때까지 기다리는 함수를 내준다.

    라운드가 닫기 시작하면 요청은 바로 돌아오고 서술은 따로 돈다.
    테스트가 "서술이 끝난 뒤"를 보려면 이것을 부른 다음에 읽는다.
    """

    async def wait() -> None:
        await app.state.jobs.drain()

    return wait


@pytest.fixture
async def readers() -> AsyncIterator[list[Reader]]:
    """이 테스트가 연 스트림들. 테스트가 끝나면 모두 끊는다."""
    opened: list[Reader] = []
    yield opened
    for reader in opened:
        await reader.close()


@pytest.fixture
def connect(app: FastAPI, readers: list[Reader]):
    """스트림을 여는 함수를 내준다. 앱의 방송실과 신호를 듣는 것을 그대로 쓴다."""

    def open_stream(table: dict, user_id: uuid.UUID, cursor: Cursor | None = None, **options) -> Reader:
        options.setdefault('heartbeat', LONG_HEARTBEAT)
        options.setdefault('source', app.state.signal_source)
        viewer = options.pop('viewer', None) or make_viewer(user_id)
        items = stream_service.stream(
            app.state.session_factory,
            app.state.hub,
            viewer=viewer,
            table_id=uuid.UUID(table['id']),
            cursor=cursor or Cursor(),
            **options,
        )
        reader = Reader(items)
        readers.append(reader)
        return reader

    return open_stream


@pytest.fixture
def spans() -> Iterator[SpanRecorder]:
    """
    테스트가 남긴 span 을 메모리에 모은다. 끝나면 아무것도 하지 않는 것으로 되돌린다.

    span 을 만드는 것은 서버에 하나라(app/observability/spans.py) 이것을 쓰는 테스트는 동시에 돌지 않는다.
    """
    with recording() as recorder:
        yield recorder
