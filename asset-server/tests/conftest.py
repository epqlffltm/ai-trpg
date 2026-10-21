# asset-server/tests/conftest.py

"""
테스트가 함께 쓰는 준비물.

pytest 는 이 파일의 fixture 를 모든 테스트 파일에서 이름만으로 쓸 수 있게 해 준다.

테스트는 실제 PostgreSQL 에서 돈다. 개발용과 같은 DB 를 쓰되 스키마를 나눈다.
개발용 데이터는 asset 스키마에, 테스트는 asset_test 스키마에 있다.
"""

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from server_core.database import create_engine
from server_core.testing.collector import Collector, serving
from server_core.testing.metrics import MetricsRecorder
from server_core.testing.metrics import recording as recording_metrics
from server_core.testing.spans import SpanRecorder, recording
from server_core.testing.tokens import FakeAuthServer, SigningKey, make_signing_key
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.main import create_app
from tests.cleaning import clear_tables
from tests.signing import TEST_AUTH_SECRET, TEST_SECRETS

TEST_SCHEMA = 'asset_test'

# 존재하지 않는 주소. 테스트는 실제 인증 서버에 요청을 보내지 않는다(server_core/testing/tokens.py 의 가짜가 받는다)
TEST_JWKS_URL = 'http://auth.test/api/v1/auth/jwks'


def make_test_settings(**overrides) -> Settings:
    """
    테스트용 설정을 만든다.

    DB 주소는 개발 환경의 것(.env 또는 환경 변수)을 그대로 읽는다. 비밀번호를 테스트 코드에 적지 않는다.
    동작을 바꾸는 값은 여기서 고정한다. 개발자의 .env 에 무엇이 적혀 있든 테스트 결과가 같아야 한다.
    """
    values = {
        'debug': False,
        # 로그는 경고부터 남긴다. 요청마다 한 줄씩 남는 것(info)까지 남기면 로그를 보는 테스트에 섞인다.
        # 요청의 줄을 보는 테스트는 그 로거의 수준을 내려서 잡는다
        'log_level': 'warning',
        'db_schema': TEST_SCHEMA,
        'auth_jwks_url': TEST_JWKS_URL,
        # span 을 내보내지 않는다. 개발자의 .env 에 수집기의 주소가 있어도 테스트는 보내지 않는다.
        # span 을 보는 테스트는 메모리에 모으는 것을 끼운다(spans fixture)
        'otel_exporter_otlp_endpoint': '',
        # 부르는 서버의 서명 비밀(tests/signing.py). 개발자의 .env 의 값과 상관없이 같다
        'chat_server_secret': TEST_SECRETS['chat'],
        'auth_server_secret': TEST_AUTH_SECRET,
    }
    values.update(overrides)
    return Settings(**values)


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
async def engine() -> AsyncIterator[AsyncEngine]:
    """
    DB 연결의 풀. 테스트 전체에서 하나를 만들어 모든 테스트의 앱이 함께 쓴다.

    테스트마다 풀을 새로 만들면 연결을 매번 새로 맺는다. 연결을 맺는 데는 왕복이 여럿 든다.
    연결은 만든 이벤트 루프에 묶이므로 테스트의 루프도 하나다(pyproject.toml).
    """
    shared = create_engine(make_test_settings())
    yield shared
    await shared.dispose()


@pytest.fixture(scope='session')
def signing_key() -> SigningKey:
    """인증 서버의 서명 키. 만드는 데 시간이 걸려서 테스트 전체에서 한 번만 만든다."""
    return make_signing_key('test-key')


@pytest.fixture
def auth_server(signing_key: SigningKey) -> FakeAuthServer:
    """가짜 인증 서버. 테스트마다 새로 만든다. 죽이거나 키를 바꿔도 다른 테스트에 번지지 않는다."""
    return FakeAuthServer(keys=[signing_key])


@pytest.fixture
async def app(settings: Settings, auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """
    테스트용 설정으로 만든 앱. 인증 서버 자리에 가짜를 꽂는다. DB 연결의 풀은 테스트 전체의 것을 쓴다(engine).

    테스트에서는 lifespan 이 돌지 않는다. 인증 서버로 가는 연결은 여기서 닫는다.
    풀은 테스트 전체가 끝날 때 engine 이 닫는다.
    """
    app = create_app(settings, http_client=auth_server.make_client(), engine=engine)
    yield app
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
async def clean_tables(engine: AsyncEngine) -> None:
    """
    테이블을 비우고 테스트를 시작한다. DB 에 쓰는 테스트가 쓴다.

    테스트를 트랜잭션으로 감싸 되돌리는 방법을 쓰지 않는다. 그러면 앱의 커밋이 진짜로 일어나지 않아,
    저장의 경계가 맞는지 볼 수 없다. 끝난 뒤가 아니라 시작할 때 비운다.
    앞의 테스트가 도중에 죽어 찌꺼기를 남겨도 영향을 받지 않는다.
    """
    await clear_tables(engine)


@pytest.fixture
def spans() -> Iterator[SpanRecorder]:
    """
    테스트가 남긴 span 을 메모리에 모은다. 끝나면 아무것도 하지 않는 것으로 되돌린다.

    span 을 만드는 것은 서버에 하나라(server_core/observability/spans.py) 이것을 쓰는 테스트는 동시에 돌지 않는다.
    """
    with recording() as recorder:
        yield recorder


@pytest.fixture
def metrics() -> Iterator[MetricsRecorder]:
    """
    테스트가 센 메트릭을 메모리에 모은다. 끝나면 아무것도 하지 않는 것으로 되돌린다.

    계측기는 서버에 한 묶음이라(server_core/observability/metrics.py) 이것을 쓰는 테스트는 동시에 돌지 않는다.
    """
    with recording_metrics() as recorder:
        yield recorder


@pytest.fixture
def collector() -> Iterator[tuple[Collector, str]]:
    """OTLP 를 받는 가짜 수집기와 그 주소(경로 없이). 보내는 길을 보는 테스트가 쓴다."""
    with serving() as served:
        yield served
