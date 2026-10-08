# game-server/tests/conftest.py

"""
테스트가 함께 쓰는 준비물.

pytest 는 이 파일의 fixture 를 모든 테스트 파일에서 이름만으로 쓸 수 있게 해 준다.

테스트는 실제 PostgreSQL 에서 돈다. 개발용과 같은 DB 를 쓰되 스키마를 나눈다.
개발용 데이터는 game 스키마에, 테스트는 game_test 스키마에 있다.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.main import create_app
from app.realtime import service as stream_service
from app.realtime.service import Cursor
from tests.signing import FakeAuthServer, SigningKey, make_signing_key, make_viewer
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
    values = {'debug': False, 'db_schema': TEST_SCHEMA, 'auth_jwks_url': TEST_JWKS_URL}
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
def signing_key() -> SigningKey:
    """인증 서버의 서명 키. 만드는 데 시간이 걸려서 테스트 전체에서 한 번만 만든다."""
    return make_signing_key('test-key')


@pytest.fixture
def auth_server(signing_key: SigningKey) -> FakeAuthServer:
    """가짜 인증 서버. 테스트마다 새로 만든다. 죽이거나 키를 바꿔도 다른 테스트에 번지지 않는다."""
    return FakeAuthServer(keys=[signing_key])


@pytest.fixture
async def app(settings: Settings, auth_server: FakeAuthServer) -> AsyncIterator[FastAPI]:
    """
    테스트용 설정으로 만든 앱. 인증 서버 자리에 가짜를 꽂는다.

    테스트가 끝나면 연결을 닫는다. 테스트에서는 lifespan 이 돌지 않으므로 직접 닫는다.
    """
    app = create_app(settings, http_client=auth_server.make_client())
    yield app
    await app.state.jobs.aclose()
    await app.state.signal_source.stop()
    await app.state.engine.dispose()
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
    """
    async with app.state.engine.begin() as connection:
        # worlds 는 assets 를 가리키므로 CASCADE 로 함께 비워진다
        await connection.execute(text('TRUNCATE TABLE assets CASCADE'))
        # 보관함은 자산을 가리키지 않아 위에서 함께 비워지지 않는다
        await connection.execute(text('TRUNCATE TABLE personas'))


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
