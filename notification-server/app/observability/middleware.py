# notification-server/app/observability/middleware.py

"""
요청마다 식별자를 정하고, 끝나면 한 줄을 남기는 미들웨어. 규격은 docs/observability.md 에 있다.

하는 일은 넷이다.
  1. 요청의 식별자(request_id)와 추적(trace_id)을 정해 건다. 밖에서 받은 값이 형식에 맞으면 이어 쓴다.
  2. 응답에 X-Request-ID 머리말로 식별자를 돌려준다. 문제를 알릴 때 이 값을 함께 알려 주면 그 요청의 기록을 찾는다.
  3. 요청이 끝나면 한 줄을 남긴다. 무엇을(메서드, 경로의 틀), 어떻게(상태 코드, 걸린 시간) 처리했는지다.
  4. 처리하지 못한 예외를 식별자와 함께 남긴다. 예외는 그대로 다시 올린다. 500 응답은 바깥(Starlette)이 만든다.

ASGI 의 모양으로 직접 썼다. Starlette 의 BaseHTTPMiddleware 는 응답을 한 번 거쳐 보내서,
이 서버의 스트림(SSE)처럼 오래 열려 있는 응답과 잘 맞지 않는다.

경로는 틀(/api/v1/game/tables/{table_id})로 적는다. 실제 주소에는 테이블의 ID 같은 값이 들어 있어서,
그대로 적으면 같은 API 가 주소마다 다른 것으로 세어진다. 맞는 틀이 없을 때(404)만 실제 경로를 따로 적는다.
요청의 머리말과 본문, 주소 뒤에 붙는 값(?a=b)은 적지 않는다.
"""

import logging
import time
from http import HTTPStatus

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.context import request_scope
from app.observability.identifiers import REQUEST_ID_HEADER, TRACEPARENT_HEADER, request_id_from, trace_from

logger = logging.getLogger(__name__)

# 요청 하나를 처리한 일의 이름
HTTP_OPERATION = 'http.request'
# 처리하지 못한 예외의 오류 코드
UNHANDLED_ERROR_CODE = 'http.unhandled_exception'
# 맞는 경로의 틀이 없을 때(404) 틀 자리에 적는 표시
UNMATCHED_ROUTE = '(unmatched)'
# 상태 확인 주소(app/api/health.py, app/api/readiness.py). 관리 도구가 10초마다 부른다.
# 요청이 끝난 줄의 수준을 따로 정한다(probe_level_of)
PROBE_ROUTES = frozenset({'/health', '/health/ready'})
# 요청의 식별자를 요청에 적어 두는 자리의 이름. 500 응답을 만드는 쪽이 여기서 읽는다(app/main.py)
SCOPE_REQUEST_ID = 'request_id'


def result_of(status_code: int) -> str:
    """상태 코드를 결과의 이름으로 바꾼다. 5xx 는 서버의 잘못, 4xx 는 요청의 잘못, 나머지는 성공이다."""
    if status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return 'server_error'
    if status_code >= HTTPStatus.BAD_REQUEST:
        return 'client_error'
    return 'success'


def level_of(route: str, status_code: int) -> int:
    """
    요청이 끝난 줄의 수준. 5xx 만 error 고 나머지는 info 다. 상태 확인 주소는 따로 본다(probe_level_of).

    4xx 는 요청이 틀린 것이다. 서버는 제 일을 했다. warning 으로 올리면 틀린 비밀번호와 없는 주소가 경고를 메운다.
    """
    if route in PROBE_ROUTES:
        return probe_level_of(status_code)
    return logging.ERROR if status_code >= HTTPStatus.INTERNAL_SERVER_ERROR else logging.INFO


def probe_level_of(status_code: int) -> int:
    """
    상태 확인 요청의 줄의 수준. 네 서버가 같다(docs/observability.md 의 "health 와 readiness").

    성공은 debug 다. 10초마다 오는 확인이 운영의 로그를 메우지 않게 한다.
    503(준비 안 됨)은 warning 이다. 오류가 아니라 이 주소의 답이다.
    까닭은 readiness 가 따로 남긴다(app/api/readiness.py).
    그 밖의 5xx(처리하지 못한 예외)는 다른 주소처럼 error 다.
    """
    if status_code == HTTPStatus.SERVICE_UNAVAILABLE:
        return logging.WARNING
    if status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return logging.ERROR
    return logging.DEBUG


def full_template(route_path: str, actual_path: str) -> str:
    """
    라우터가 알려 준 경로의 틀에 앞부분(/api/v1/game)을 붙여 전체 틀을 만든다.

    라우터를 앞부분과 함께 붙이면(include_router(prefix=...)) 맞은 경로의 틀에는 앞부분이 빠져 있다.
    틀의 마디 수만큼을 실제 경로의 뒤에서 떼면 남는 것이 앞부분이다. 이 서버의 앞부분에는 바뀌는 값이 없다.
    여러 마디를 한꺼번에 받는 틀({name:path})이면 마디 수를 셀 수 없다. 그때는 받은 틀을 그대로 쓴다.
    """
    tail = [part for part in route_path.split('/') if part]
    actual = [part for part in actual_path.split('/') if part]
    if ':path}' in route_path or len(tail) > len(actual):
        return route_path
    return '/' + '/'.join(actual[: len(actual) - len(tail)] + tail)


def route_fields(scope: Scope) -> dict[str, str]:
    """
    요청이 맞은 경로의 틀. 맞은 것이 없으면(404) 틀 자리에 표시를 적고 실제 경로를 따로 싣는다.

    라우터는 요청을 처리하면서 맞은 경로를 scope 에 적어 둔다. 그래서 처리가 끝난 뒤에 읽는다.
    """
    path = str(scope.get('path', ''))
    template = getattr(scope.get('route'), 'path', None)
    if isinstance(template, str):
        return {'route': full_template(template, path)}
    return {'route': UNMATCHED_ROUTE, 'path': path}


def single_header(headers: Headers, name: str) -> str | None:
    """머리말의 값을 돌려준다. 같은 머리말이 여러 번 왔으면 None 이다. 어느 것을 믿을지 정할 수 없다."""
    values = headers.getlist(name)
    return values[0] if len(values) == 1 else None


def request_fields(scope: Scope, status_code: int, started: float) -> dict[str, object]:
    """요청이 끝난 줄에 싣는 칸들."""
    return {
        'operation': HTTP_OPERATION,
        'method': scope.get('method', ''),
        **route_fields(scope),
        'status_code': status_code,
        'duration_ms': round((time.perf_counter() - started) * 1000),
        'result': result_of(status_code),
    }


class RequestLoggingMiddleware:
    """요청마다 식별자를 걸고, 끝나면 공통 규격의 한 줄을 남긴다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = request_id_from(single_header(headers, REQUEST_ID_HEADER))
        trace = trace_from(single_header(headers, TRACEPARENT_HEADER))
        scope[SCOPE_REQUEST_ID] = request_id
        started = time.perf_counter()
        # 응답이 시작될 때의 상태 코드. 응답이 시작되기 전에 예외가 나면 비어 있다
        seen: dict[str, int] = {}

        async def send_with_request_id(message: Message) -> None:
            if message['type'] == 'http.response.start':
                seen['status_code'] = message['status']
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        with request_scope(request_id, trace):
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception:
                status_code = seen.get('status_code', HTTPStatus.INTERNAL_SERVER_ERROR)
                self.log_unhandled(scope)
                self.log_finished(scope, max(status_code, HTTPStatus.INTERNAL_SERVER_ERROR), started)
                raise
            self.log_finished(scope, seen.get('status_code', HTTPStatus.INTERNAL_SERVER_ERROR), started)

    def log_finished(self, scope: Scope, status_code: int, started: float) -> None:
        """요청이 끝났다는 한 줄을 남긴다."""
        fields = request_fields(scope, status_code, started)
        logger.log(level_of(fields['route'], status_code), '요청을 처리했다', extra=fields)

    def log_unhandled(self, scope: Scope) -> None:
        """처리하지 못한 예외를 남긴다. 예외를 잡은 자리(except 안)에서 부른다. 예외의 기록이 함께 실린다."""
        logger.error(
            '요청을 처리하다 예외가 났다',
            exc_info=True,
            extra={
                'operation': HTTP_OPERATION,
                'error_code': UNHANDLED_ERROR_CODE,
                'method': scope.get('method', ''),
                **route_fields(scope),
            },
        )
