# game-server/tests/conftest.py

"""
테스트가 함께 쓰는 준비물.

pytest 는 이 파일의 fixture 를 모든 테스트 파일에서 이름만으로 쓸 수 있게 해 준다.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


def make_client(app: FastAPI) -> AsyncClient:
    """
    앱에 요청을 보내는 클라이언트를 만든다.

    서버를 실제로 띄우지 않는다. 요청을 네트워크 없이 앱에 바로 넘긴다.
    """
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver')


@pytest.fixture
def settings() -> Settings:
    """
    테스트용 설정. .env 파일을 읽지 않는다.

    개발자의 .env 에 무엇이 적혀 있든 테스트 결과가 같아야 한다.
    """
    return Settings(_env_file=None)


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """테스트용 설정으로 만든 앱에 요청을 보내는 클라이언트."""
    async with make_client(create_app(settings)) as test_client:
        yield test_client
