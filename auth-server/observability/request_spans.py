# auth-server/observability/request_spans.py

"""
요청마다 서버 span 을 거는 미들웨어. 설정의 MIDDLEWARE 맨 앞에 둔다. 안의 로그와 쿼리가 이 span 아래에 놓인다.

이름은 메서드와 경로의 틀이다(POST /api/v1/auth/login). 실제 주소가 아니다. 맞은 것이 없으면(404) (unmatched) 다.
틀은 Django 가 요청을 처리한 뒤에 알 수 있다(resolver_match). 그래서 메서드만으로 시작하고 끝날 때 이름을 고친다.

받은 traceparent 가 형식에 맞으면 그 아래에 붙는다(부른 서버의 span 이 부모가 된다). 받는 규칙은 로그와 같다.
상태 확인(/health, /health/ready)은 span 을 걸지 않는다. 10초마다 오는 확인이 추적을 메우지 않게 한다.
span 에는 메서드, 경로의 틀, 상태 코드, 요청 식별자만 싣는다. 머리말, 주소 뒤의 값, 본문, 예외의 글은 싣지 않는다.
본문에는 비밀번호와 인증 코드가 들어 있다.

뷰에서 난 예외는 Django 가 500 응답으로 바꿔 돌려준다. 여기까지 예외로 올라오지 않는다. 응답의 상태 코드로 본다.
"""

from http import HTTPStatus

from opentelemetry.trace import Span, SpanKind, StatusCode

from observability.identifiers import TRACEPARENT_HEADER
from observability.middleware import PROBE_ROUTES, route_fields
from observability.spans import remote_parent, tracer


def finish_server_span(span: Span, request, status_code: int) -> None:
    """끝난 요청을 span 에 적는다. 이름을 경로의 틀로 고친다. 서버의 잘못(5xx)만 오류로 표시한다."""
    route = route_fields(request)['route']
    span.update_name(f'{request.method} {route}')
    span.set_attribute('http.route', route)
    span.set_attribute('http.response.status_code', status_code)
    if status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        span.set_status(StatusCode.ERROR, HTTPStatus(status_code).phrase)


class RequestSpanMiddleware:
    """요청마다 서버 span 을 건다. 보낼 곳이 없으면(NoOp) 아무것도 남지 않는다."""

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        if request.path in PROBE_ROUTES:
            return self.get_response(request)
        with tracer().start_as_current_span(
            request.method,
            context=remote_parent(request.headers.get(TRACEPARENT_HEADER)),
            kind=SpanKind.SERVER,
            attributes={'http.request.method': request.method},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            response = self.get_response(request)
            finish_server_span(span, request, response.status_code)
            return response
