# board-server/tests/conftest.py

"""
테스트가 함께 쓰는 준비물.

테스트는 실제 PostgreSQL 에서 돈다. 개발용과 같은 DB 를 쓰되 스키마를 나눈다(board_test).
주소와 응답의 시나리오는 계약 시험(contract/)이 서버를 띄워 본다. 여기서는 HTTP 만으로 볼 수 없는 것을 본다:
설정, 오류의 모양, 인증 서버가 없을 때, DB 에 닿지 않을 때, 검색의 시간 초과, 메트릭, 알림 보내기, DB 권한.
"""

from collections.abc import AsyncIterator, Callable, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from server_core.database import create_engine
from server_core.testing.metrics import MetricsRecorder
from server_core.testing.metrics import recording as recording_metrics
from server_core.testing.tokens import FakeAuthServer, SigningKey, make_access_claims, make_signing_key, make_token
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.main import create_app
from tests.cleaning import clear_tables

TEST_SCHEMA = 'board_test'

# 존재하지 않는 주소. 테스트는 실제 인증 서버에 요청을 보내지 않는다(server_core/testing/tokens.py 의 가짜가 받는다)
TEST_JWKS_URL = 'http://auth.test/api/v1/auth/jwks'
# 인증 서버의 테스트용 서명 비밀(탈퇴 알림). 32자 이상이다
TEST_AUTH_SECRET = 'test-auth-secret-0123456789abcdef'


def make_test_settings(**overrides) -> Settings:
    """
    테스트용 설정을 만든다.

    DB 주소는 개발 환경의 것(.env 또는 환경 변수)을 그대로 읽는다. 비밀번호를 테스트 코드에 적지 않는다.
    동작을 바꾸는 값은 여기서 고정한다. 개발자의 .env 에 무엇이 적혀 있든 테스트 결과가 같아야 한다.
    """
    values = {
        'debug': False,
        'log_level': 'warning',
        'db_schema': TEST_SCHEMA,
        'auth_jwks_url': TEST_JWKS_URL,
        'otel_exporter_otlp_endpoint': '',
        'auth_server_secret': TEST_AUTH_SECRET,
        # 알림 서버로 보내지 않는다. 발송함에 적기만 한다
        'notification_url': '',
    }
    values.update(overrides)
    return Settings(**values)


def make_client(app: FastAPI) -> AsyncClient:
    """앱에 요청을 보내는 클라이언트. 서버를 띄우지 않고 요청을 바로 넘긴다."""
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver')


@pytest.fixture
def settings() -> Settings:
    settings = make_test_settings()
    assert settings.db_schema.endswith('_test'), '테스트는 테스트용 스키마에서만 돈다'
    return settings


@pytest.fixture(scope='session')
async def engine() -> AsyncIterator[AsyncEngine]:
    """DB 연결의 풀. 테스트 전체에서 하나를 만들어 모든 테스트의 앱이 함께 쓴다."""
    shared = create_engine(make_test_settings())
    yield shared
    await shared.dispose()


@pytest.fixture(scope='session')
def signing_key() -> SigningKey:
    """인증 서버의 서명 키. 만드는 데 시간이 걸려서 테스트 전체에서 한 번만 만든다."""
    return make_signing_key('test-key')


@pytest.fixture
def auth_server(signing_key: SigningKey) -> FakeAuthServer:
    """가짜 인증 서버. 테스트마다 새로 만든다."""
    return FakeAuthServer(keys=[signing_key])


@pytest.fixture
async def app(settings: Settings, auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """테스트용 설정으로 만든 앱. 인증 서버 자리에 가짜를 꽂는다. lifespan 은 돌지 않는다."""
    app = create_app(settings, http_client=auth_server.make_client(), engine=engine)
    yield app
    await app.state.http_client.aclose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with make_client(app) as test_client:
        yield test_client


@pytest.fixture
async def session(app: FastAPI) -> AsyncIterator[AsyncSession]:
    """테스트가 DB 를 직접 들여다볼 때 쓰는 세션."""
    async with app.state.session_factory() as db_session:
        yield db_session


@pytest.fixture
async def clean_tables(engine: AsyncEngine) -> None:
    """데이터를 비우고 테스트를 시작한다. 게시판은 마이그레이션이 넣은 것이라 두고 간다."""
    await clear_tables(engine)


@pytest.fixture
def headers_for(signing_key: SigningKey) -> Callable[..., dict[str, str]]:
    """그 사람의 토큰을 실은 머리말. 토큰의 칸은 키워드로 바꾼다(make_access_claims)."""

    def make(subject: str, **claims) -> dict[str, str]:
        token = make_token(signing_key, make_access_claims(sub=subject, **claims))
        return {'Authorization': f'Bearer {token}'}

    return make


@pytest.fixture
def metrics() -> Iterator[MetricsRecorder]:
    """테스트가 센 메트릭을 메모리에 모은다. 끝나면 아무것도 하지 않는 것으로 되돌린다."""
    with recording_metrics() as recorder:
        yield recorder
