# game-server/tests/test_app.py

"""
앱을 만드는 설정을 검증한다. API 문서 화면이 언제 열리는가.
"""

from fastapi import status

from app.core.config import Settings
from app.main import API_PREFIX, create_app
from tests.conftest import make_client

DOCS_URL = f'{API_PREFIX}/docs'
OPENAPI_URL = f'{API_PREFIX}/openapi.json'


async def test_docs_are_closed_by_default():
    app = create_app(Settings(_env_file=None))

    async with make_client(app) as client:
        docs = await client.get(DOCS_URL)
        openapi = await client.get(OPENAPI_URL)

    # 운영 서버에서 API 의 구조를 내보이지 않는다
    assert docs.status_code == status.HTTP_404_NOT_FOUND
    assert openapi.status_code == status.HTTP_404_NOT_FOUND


async def test_docs_open_when_debugging():
    app = create_app(Settings(_env_file=None, debug=True))

    async with make_client(app) as client:
        docs = await client.get(DOCS_URL)
        openapi = await client.get(OPENAPI_URL)

    assert docs.status_code == status.HTTP_200_OK
    assert openapi.status_code == status.HTTP_200_OK


async def test_default_docs_address_is_not_used():
    app = create_app(Settings(_env_file=None, debug=True))

    async with make_client(app) as client:
        response = await client.get('/docs')

    # 문서 화면도 이 서버의 API 주소 아래에 둔다. 프록시가 주소 앞부분으로 서버를 가른다
    assert response.status_code == status.HTTP_404_NOT_FOUND
