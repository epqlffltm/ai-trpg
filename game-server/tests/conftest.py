# game-server/tests/conftest.py

"""
테스트가 함께 쓰는 준비물.

pytest 는 이 파일의 fixture 를 모든 테스트 파일에서 이름만으로 쓸 수 있게 해 준다.

테스트는 실제 PostgreSQL 에서 돈다. 개발용과 같은 DB 를 쓰되 스키마를 나눈다.
개발용 데이터는 game 스키마에, 테스트는 game_test 스키마에 있다.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.main import create_app

TEST_SCHEMA = 'game_test'


def make_test_settings(**overrides) -> Settings:
    """
    테스트용 설정을 만든다.

    DB 주소는 개발 환경의 것(.env 또는 환경 변수)을 그대로 읽는다. 비밀번호를 테스트 코드에 적지 않는다.
    동작을 바꾸는 값은 여기서 고정한다. 개발자의 .env 에 무엇이 적혀 있든 테스트 결과가 같아야 한다.
    """
    values = {'debug': False, 'db_schema': TEST_SCHEMA}
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


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    """테스트용 설정으로 만든 앱. 테스트가 끝나면 DB 연결을 닫는다."""
    app = create_app(settings)
    yield app
    await app.state.engine.dispose()


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
