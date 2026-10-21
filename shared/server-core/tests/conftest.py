# shared/server-core/tests/conftest.py

"""
공용 코드의 테스트가 함께 쓰는 준비물.

DB 없이 돈다. DB 에 닿는 것(쿼리의 span, 연결 풀의 메트릭, 스키마)은 그것을 쓰는 서버의 테스트가 실제 DB 로 본다.
토큰을 받는 API 는 이 파일의 작은 앱(app fixture)으로 본다. 서버의 앱과 같은 자리(app.state)에 같은 것을 붙인다.
"""

from collections.abc import AsyncIterator, Iterator
from typing import ClassVar

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from server_core.auth.dependencies import CurrentUser, OptionalUser
from server_core.auth.jwks import JwksCache
from server_core.auth.revocations import RevocationList
from server_core.settings import CoreSettings
from server_core.testing.collector import Collector, serving
from server_core.testing.metrics import MetricsRecorder
from server_core.testing.metrics import recording as recording_metrics
from server_core.testing.spans import SpanRecorder, recording
from server_core.testing.tokens import FakeAuthServer, SigningKey, make_signing_key

# 존재하지 않는 주소. 테스트는 실제 인증 서버에 요청을 보내지 않는다(server_core/testing/tokens.py 의 가짜가 받는다)
TEST_JWKS_URL = 'http://auth.test/api/v1/auth/jwks'
# 테스트의 작은 앱이 내는 주소
ME_URL = '/me'
OPTIONAL_URL = '/maybe-me'


class TestSettings(CoreSettings):
    """공용 코드의 테스트가 쓰는 설정. 서버의 설정처럼 이름과 기본값을 준다. 대상은 실제 서버 하나의 이름을 빌린다."""

    __test__ = False
    service_name: ClassVar[str] = 'test-server'
    db_schema: str = 'core_test'
    jwt_audience: str = 'ai-trpg-asset'


def make_test_settings(**overrides) -> TestSettings:
    """
    테스트용 설정을 만든다. 개발자의 .env 와 환경 변수에 무엇이 있든 같은 값이다.

    DB 주소는 쓰지 않는다(연결하지 않는다). 형식만 맞춘다.
    """
    values = {
        'debug': False,
        'log_level': 'warning',
        'database_url': 'postgresql+asyncpg://core:pw@127.0.0.1:5432/trpg',
        'auth_jwks_url': TEST_JWKS_URL,
        'otel_exporter_otlp_endpoint': '',
    }
    values.update(overrides)
    return TestSettings(_env_file=None, **values)


def make_client(app: FastAPI) -> AsyncClient:
    """앱에 요청을 보내는 클라이언트. 서버를 띄우지 않고 요청을 바로 넘긴다."""
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver')


async def read_me(user: CurrentUser) -> dict:
    """로그인이 필요한 주소. 토큰의 주인을 돌려준다."""
    return {'user_id': str(user.user_id), 'adult_content': user.adult_content, 'is_operator': user.is_operator}


async def read_maybe_me(user: OptionalUser) -> dict:
    """로그인 없이도 읽는 주소. 로그인하지 않았으면 user_id 가 null 이다."""
    return {'user_id': str(user.user_id) if user else None}


def build_app(settings: TestSettings, auth_server: FakeAuthServer) -> FastAPI:
    """토큰을 받는 작은 앱. 서버의 앱과 같은 자리(app.state)에 설정, 공개키, 끊긴 세션의 목록을 붙인다."""
    app = FastAPI()
    client = auth_server.make_client()
    app.state.settings = settings
    app.state.http_client = client
    app.state.jwks = JwksCache(client, settings.auth_jwks_url)
    app.state.revocations = RevocationList(client, settings.session_revocations_url)
    app.add_api_route(ME_URL, read_me, methods=['GET'], status_code=status.HTTP_200_OK)
    app.add_api_route(OPTIONAL_URL, read_maybe_me, methods=['GET'], status_code=status.HTTP_200_OK)
    return app


@pytest.fixture
def settings() -> TestSettings:
    """테스트용 설정."""
    return make_test_settings()


@pytest.fixture(scope='session')
def signing_key() -> SigningKey:
    """인증 서버의 서명 키. 만드는 데 시간이 걸려서 테스트 전체에서 한 번만 만든다."""
    return make_signing_key('test-key')


@pytest.fixture
def auth_server(signing_key: SigningKey) -> FakeAuthServer:
    """가짜 인증 서버. 테스트마다 새로 만든다."""
    return FakeAuthServer(keys=[signing_key])


@pytest.fixture
async def app(settings: TestSettings, auth_server: FakeAuthServer) -> AsyncIterator[FastAPI]:
    """토큰을 받는 작은 앱."""
    built = build_app(settings, auth_server)
    yield built
    await built.state.http_client.aclose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """작은 앱에 요청을 보내는 클라이언트."""
    async with make_client(app) as test_client:
        yield test_client


@pytest.fixture
def spans() -> Iterator[SpanRecorder]:
    """테스트가 남긴 span 을 메모리에 모은다. 이것을 쓰는 테스트는 동시에 돌지 않는다."""
    with recording() as recorder:
        yield recorder


@pytest.fixture
def metrics() -> Iterator[MetricsRecorder]:
    """테스트가 센 메트릭을 메모리에 모은다. 이것을 쓰는 테스트는 동시에 돌지 않는다."""
    with recording_metrics() as recorder:
        yield recorder


@pytest.fixture
def collector() -> Iterator[tuple[Collector, str]]:
    """OTLP 를 받는 가짜 수집기와 그 주소(경로 없이)."""
    with serving() as served:
        yield served
