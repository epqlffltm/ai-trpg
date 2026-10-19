# auth-server/observability/middleware.py

"""
요청마다 식별자를 정하고, 끝나면 한 줄을 남기는 미들웨어. 규격은 docs/observability.md 에 있다.

하는 일은 넷이다.
  1. 요청의 식별자(request_id)와 추적(trace_id)을 정해 건다. 밖에서 받은 값이 형식에 맞으면 이어 쓴다.
  2. 응답에 X-Request-ID 머리말로 식별자를 돌려준다. 문제를 알릴 때 이 값을 함께 알려 주면 그 요청의 기록을 찾는다.
  3. 요청이 끝나면 한 줄을 남긴다. 무엇을(메서드, 경로의 틀), 어떻게(상태 코드, 걸린 시간) 처리했는지다.
  4. 뷰에서 난, 처리하지 못한 예외를 식별자와 함께 남긴다. 500 응답은 Django 가 만든다.

설정의 MIDDLEWARE 맨 앞에 둔다. 다른 미들웨어가 남기는 로그에도 식별자가 붙고, 다른 미들웨어가 만든 응답
(403, 404)에도 머리말이 붙는다.

경로는 틀(api/v1/auth/login)로 적는다. 맞는 틀이 없을 때(404)만 실제 경로를 따로 적는다.
요청의 머리말과 본문, 주소 뒤에 붙는 값(?a=b)은 적지 않는다. 본문에는 비밀번호와 인증 코드가 들어 있다.
"""

import logging
import time
from http import HTTPStatus

from observability.context import request_scope
from observability.identifiers import REQUEST_ID_HEADER, TRACEPARENT_HEADER, Trace, request_id_from, trace_from
from observability.setup import LOGGED_UNHANDLED_ATTRIBUTE
from observability.spans import ATTRIBUTE_REQUEST_ID, span_trace, tag_current_span

logger = logging.getLogger(__name__)

# 요청 하나를 처리한 일의 이름
HTTP_OPERATION = 'http.request'
# 처리하지 못한 예외의 오류 코드
UNHANDLED_ERROR_CODE = 'http.unhandled_exception'
# 맞는 경로의 틀이 없을 때(404) 틀 자리에 적는 표시
UNMATCHED_ROUTE = '(unmatched)'
# 상태 확인 주소(config/health.py). 관리 도구가 10초마다 부른다. 요청이 끝난 줄의 수준을 따로 정한다
PROBE_ROUTES = frozenset({'/health', '/health/ready'})


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
    503(준비 안 됨)은 warning 이다. 오류가 아니라 이 주소의 답이다. 까닭은 readiness 가 따로 남긴다(config/health.py).
    그 밖의 5xx(처리하지 못한 예외)는 다른 주소처럼 error 다.
    """
    if status_code == HTTPStatus.SERVICE_UNAVAILABLE:
        return logging.WARNING
    if status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return logging.ERROR
    return logging.DEBUG


def route_fields(request) -> dict[str, str]:
    """
    요청이 맞은 경로의 틀. 맞은 것이 없으면(404) 틀 자리에 표시를 적고 실제 경로를 따로 싣는다.

    Django 는 요청을 처리하면서 맞은 경로를 요청에 적어 둔다(resolver_match). 그래서 처리가 끝난 뒤에 읽는다.
    """
    match = getattr(request, 'resolver_match', None)
    template = getattr(match, 'route', None)
    if isinstance(template, str) and template:
        return {'route': '/' + template.lstrip('/')}
    return {'route': UNMATCHED_ROUTE, 'path': request.path}


def trace_of_request(request) -> Trace:
    """
    요청이 속한 추적. 서버 span 이 걸려 있으면(request_spans.py) 그 span 의 것이라 로그와 추적이 같은 번호다.

    없으면(상태 확인, span 을 내보내지 않는 PC) 받은 traceparent 를 이어 가거나 새로 시작한다.
    """
    return span_trace() or trace_from(request.headers.get(TRACEPARENT_HEADER))


def request_fields(request, status_code: int, started: float) -> dict[str, object]:
    """요청이 끝난 줄에 싣는 칸들."""
    return {
        'operation': HTTP_OPERATION,
        'method': request.method,
        **route_fields(request),
        'status_code': status_code,
        'duration_ms': round((time.perf_counter() - started) * 1000),
        'result': result_of(status_code),
    }


class RequestLoggingMiddleware:
    """요청마다 식별자를 걸고, 끝나면 공통 규격의 한 줄을 남긴다."""

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        request_id = request_id_from(request.headers.get(REQUEST_ID_HEADER))
        trace = trace_of_request(request)
        # 서버 span 에 요청 식별자를 싣는다. 응답의 X-Request-ID 로 Tempo 에서 그 요청을 찾는다
        tag_current_span(ATTRIBUTE_REQUEST_ID, request_id)
        started = time.perf_counter()

        with request_scope(request_id, trace):
            # 뷰에서 예외가 나도 Django 가 500 응답으로 바꿔서 돌려준다. 여기까지 예외로 올라오지 않는다
            response = self.get_response(request)
            response[REQUEST_ID_HEADER] = request_id
            status_code = response.status_code
            fields = request_fields(request, status_code, started)
            logger.log(level_of(fields['route'], status_code), '요청을 처리했다', extra=fields)
        return response

    def process_exception(self, request, exception) -> None:
        """
        뷰에서 처리하지 못한 예외가 났을 때 Django 가 부른다. 식별자와 함께 남기고, 처리는 Django 에 맡긴다.

        요청에 "내가 적었다"는 표시를 남긴다. Django 가 같은 예외를 다시 적는 줄을 그 표시로 버린다(setup.py).
        """
        setattr(request, LOGGED_UNHANDLED_ATTRIBUTE, True)
        logger.error(
            '요청을 처리하다 예외가 났다',
            exc_info=(type(exception), exception, exception.__traceback__),
            extra={
                'operation': HTTP_OPERATION,
                'error_code': UNHANDLED_ERROR_CODE,
                'method': request.method,
                **route_fields(request),
            },
        )
