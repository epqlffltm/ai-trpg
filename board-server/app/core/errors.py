# board-server/app/core/errors.py

"""
오류 응답의 모양. 오류는 언제나 {"detail": "문장"} 이다(docs/api/README.md 의 "오류의 모양").

    {"detail": "입력이 올바르지 않습니다.", "errors": {"title": ["제목을 적어야 합니다."]}}   입력 오류(400)
    {"detail": "글을 너무 자주 쓰고 있습니다. ...", "retry_after": 142}                   너무 자주(429, Retry-After)

  - 이 서버의 거절은 ApiError 로 던진다. 문장과 상태 코드, 기다릴 초를 싣는다
  - FastAPI 와 Starlette 가 만든 거절(없는 주소 404, 허용하지 않는 메서드 405)은 상태 코드에 맞는 문장으로 바꾼다.
    라이브러리의 글(Not Found)을 그대로 내보내지 않는다
  - 입력 오류의 코드는 400 이다. 이 서버가 NestJS 로 쓰던 때부터의 계약이다(FastAPI 서버들은 422).
    본문은 서버들이 함께 쓰는 모양이다(server_core/input_errors.py)
  - 본문이 JSON 이 아니면 칸을 가르지 않고 400 {"detail"} 이다. 파서의 글을 싣지 않는다
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from server_core.input_errors import JSON_INVALID_TYPE, input_error_body, replace_validation_schemas
from starlette.exceptions import HTTPException as StarletteHTTPException

# 입력 오류의 상태 코드. 이 서버의 계약이다(프레임워크를 바꿔도 지킨다)
INPUT_ERROR_STATUS = status.HTTP_400_BAD_REQUEST

# 상태 코드마다의 기본 문장. 거절이 문장을 싣지 않았을 때 쓴다
DEFAULT_DETAILS = {
    status.HTTP_400_BAD_REQUEST: '요청이 올바르지 않습니다.',
    status.HTTP_401_UNAUTHORIZED: '인증이 필요합니다.',
    status.HTTP_403_FORBIDDEN: '권한이 없습니다.',
    status.HTTP_404_NOT_FOUND: '찾을 수 없습니다.',
    status.HTTP_405_METHOD_NOT_ALLOWED: '허용되지 않는 요청입니다.',
    status.HTTP_409_CONFLICT: '요청이 지금 상태와 맞지 않습니다.',
    status.HTTP_413_CONTENT_TOO_LARGE: '요청이 너무 큽니다.',
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: '지원하지 않는 형식입니다.',
    status.HTTP_429_TOO_MANY_REQUESTS: '요청이 너무 많습니다.',
    status.HTTP_503_SERVICE_UNAVAILABLE: '지금은 요청을 처리할 수 없습니다.',
}
CLIENT_ERROR_DETAIL = '요청을 처리할 수 없습니다.'
SERVER_ERROR_DETAIL = '서버에서 오류가 났습니다.'


class ApiError(Exception):
    """이 서버의 거절. 문장(detail)과 상태 코드, 너무 자주일 때 기다릴 초(retry_after)를 싣는다."""

    def __init__(self, status_code: int, detail: str, *, retry_after: int | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after


def default_detail(status_code: int) -> str:
    """상태 코드에 맞는 기본 문장."""
    known = DEFAULT_DETAILS.get(status_code)
    if known is not None:
        return known
    return SERVER_ERROR_DETAIL if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR else CLIENT_ERROR_DETAIL


def is_library_phrase(status_code: int, detail: Any) -> bool:
    """라이브러리가 붙인 글(Not Found 같은 상태 코드의 이름)인가. 그러면 이 서버의 문장으로 바꾼다."""
    try:
        return detail == HTTPStatus(status_code).phrase
    except ValueError:
        return False


def detail_of(status_code: int, detail: Any) -> str:
    """응답에 실을 문장. 글이 아니거나 라이브러리의 글이면 기본 문장이다."""
    if isinstance(detail, str) and detail and not is_library_phrase(status_code, detail):
        return detail
    return default_detail(status_code)


async def handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    """이 서버의 거절을 응답으로. 기다릴 초가 있으면 본문과 Retry-After 머리말에 싣는다."""
    assert isinstance(exc, ApiError)
    body: dict[str, Any] = {'detail': exc.detail}
    headers: dict[str, str] = {}
    if exc.retry_after is not None:
        body['retry_after'] = exc.retry_after
        headers['Retry-After'] = str(exc.retry_after)
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    """FastAPI 와 Starlette 의 거절을 응답으로. 붙은 머리말(WWW-Authenticate, Retry-After)은 그대로 둔다."""
    assert isinstance(exc, StarletteHTTPException)
    return JSONResponse(
        status_code=exc.status_code,
        content={'detail': detail_of(exc.status_code, exc.detail)},
        headers=getattr(exc, 'headers', None),
    )


async def handle_invalid_input(request: Request, exc: Exception) -> JSONResponse:
    """입력 오류를 400 으로. 본문이 JSON 이 아니면 칸을 가르지 않는다."""
    assert isinstance(exc, RequestValidationError)
    errors = exc.errors()
    if any(error.get('type') == JSON_INVALID_TYPE for error in errors):
        return JSONResponse(status_code=INPUT_ERROR_STATUS, content={'detail': default_detail(INPUT_ERROR_STATUS)})
    return JSONResponse(status_code=INPUT_ERROR_STATUS, content=input_error_body(errors))


def use_error_bodies(app: FastAPI) -> None:
    """앱의 거절을 이 서버의 모양으로 답하게 하고 API 목록의 입력 오류도 그 모양(400)으로 적는다."""
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_invalid_input)
    build_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = build_openapi()
        replace_validation_schemas(schema, INPUT_ERROR_STATUS)
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
