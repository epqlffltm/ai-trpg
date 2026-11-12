# shared/server-core/src/server_core/error_handlers.py

"""
서버의 오류를 HTTP 응답으로 바꾸는 처리기를 앱에 거는 것.

Starlette 의 처리기 타입(ExceptionHandler)은 오류를 Exception 으로만 받는다. 그런데 처리기는 거는 오류의 종류만 받는다.
처리기마다 Exception 으로 받아 다시 좁히거나, 거는 줄마다 타입 검사를 끄지 않게, 오류의 종류와 처리기가 짝이
맞는지를 여기서 한 번 보고 건다. 짝이 틀리면(다른 오류의 처리기) 타입 검사가 잡는다.
"""

from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request
from starlette.responses import Response
from starlette.types import ExceptionHandler


def add_error_handler[E: Exception](
    app: FastAPI, error_type: type[E], handler: Callable[[Request, E], Awaitable[Response]]
) -> None:
    """error_type 의 오류가 나면 handler 의 응답을 돌려준다. 그 종류의 오류만 오므로 좁혀 받은 처리기를 건다."""
    app.add_exception_handler(error_type, cast(ExceptionHandler, handler))
