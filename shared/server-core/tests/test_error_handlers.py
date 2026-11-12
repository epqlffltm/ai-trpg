# shared/server-core/tests/test_error_handlers.py

"""
오류의 처리기를 거는 것(server_core/error_handlers.py)을 검증한다.

보는 것.
  - 건 종류의 오류가 나면 그 처리기의 응답이다. 처리기는 그 오류의 값을 읽는다
  - 그 종류를 물려받은 오류에도 같은 처리기가 불린다(Starlette 의 규칙)
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from server_core.error_handlers import add_error_handler


class ShelfFullError(Exception):
    """처리기가 값을 읽는 오류."""

    def __init__(self, limit: int) -> None:
        super().__init__(limit)
        self.limit = limit


class TinyShelfError(ShelfFullError):
    """물려받은 오류."""


async def handle_shelf_full(request: Request, error: ShelfFullError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={'limit': error.limit})


def shelf_app() -> FastAPI:
    """오류를 내는 주소 둘을 가진 앱."""
    app = FastAPI()
    add_error_handler(app, ShelfFullError, handle_shelf_full)

    @app.get('/full', status_code=status.HTTP_200_OK)
    async def full() -> None:
        raise ShelfFullError(3)

    @app.get('/tiny', status_code=status.HTTP_200_OK)
    async def tiny() -> None:
        raise TinyShelfError(1)

    return app


async def test_the_handler_answers_its_error():
    async with AsyncClient(transport=ASGITransport(app=shelf_app()), base_url='http://test') as client:
        full = await client.get('/full')
        tiny = await client.get('/tiny')

    assert (full.status_code, full.json()) == (status.HTTP_409_CONFLICT, {'limit': 3})
    assert (tiny.status_code, tiny.json()) == (status.HTTP_409_CONFLICT, {'limit': 1})
