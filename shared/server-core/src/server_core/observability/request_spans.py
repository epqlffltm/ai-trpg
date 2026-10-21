# shared/server-core/src/server_core/observability/request_spans.py

"""
요청마다 서버 span 을 거는 미들웨어. 서버의 app/main.py 가 붙인다. 안의 로그와 쿼리가 이 span 아래에 놓인다.

이름은 메서드와 경로의 틀이다(GET /api/v1/game/tables/{table_id}). 실제 주소가 아니다.
맞은 것이 없으면(404) (unmatched) 다.
틀은 라우터가 요청을 처리한 뒤에 알 수 있다. 그래서 메서드만으로 시작하고 끝날 때 이름을 고친다.

받은 traceparent 가 형식에 맞으면 그 아래에 붙는다(부른 서버의 span 이 부모가 된다). 받는 규칙은 로그와 같다.
상태 확인(/health, /health/ready)은 span 을 걸지 않는다. 10초마다 오는 확인이 추적을 메우지 않게 한다.
서버가 넘긴 스트림(SSE, streams.py)도 걸지 않는다. 응답이 몇 시간씩 끝나지 않고,
그동안 새 이벤트마다 도는 쿼리가 모두 한 span 아래에 쌓여 추적 하나가 끝없이 길어진다.
span 에는 메서드, 경로의 틀, 상태 코드, 요청 식별자만 싣는다. 머리말, 주소 뒤의 값, 본문, 예외의 글은 싣지 않는다.
"""

from http import HTTPStatus

from opentelemetry.trace import Span, SpanKind, StatusCode
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from server_core.observability.identifiers import TRACEPARENT_HEADER
from server_core.observability.middleware import PROBE_ROUTES, route_fields, single_header
from server_core.observability.spans import remote_parent, tracer
from server_core.observability.streams import NO_STREAMS, StreamRoutes


def is_stream(scope: Scope, streams: StreamRoutes) -> bool:
    """스트림(SSE)을 여는 요청인가. 실제 경로로 본다. 요청의 메트릭(request_metrics.py)도 쓴다."""
    return streams.matches(str(scope.get('path', '')))


def is_untraced(scope: Scope, streams: StreamRoutes) -> bool:
    """span 을 걸지 않는 주소인가. 상태 확인과 스트림이다. 둘 다 실제 경로로 본다."""
    return str(scope.get('path', '')) in PROBE_ROUTES or is_stream(scope, streams)


def finish_server_span(span: Span, scope: Scope, status_code: int) -> None:
    """끝난 요청을 span 에 적는다. 이름을 경로의 틀로 고친다. 서버의 잘못(5xx)만 오류로 표시한다."""
    method = str(scope.get('method', ''))
    route = route_fields(scope)['route']
    span.update_name(f'{method} {route}')
    span.set_attribute('http.route', route)
    span.set_attribute('http.response.status_code', status_code)
    if status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        span.set_status(StatusCode.ERROR, HTTPStatus(status_code).phrase)


class RequestSpanMiddleware:
    """요청마다 서버 span 을 건다. 보낼 곳이 없으면(NoOp) 아무것도 남지 않는다. streams 는 걸지 않을 스트림이다."""

    def __init__(self, app: ASGIApp, streams: StreamRoutes = NO_STREAMS) -> None:
        self.app = app
        self.streams = streams

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or is_untraced(scope, self.streams):
            await self.app(scope, receive, send)
            return

        method = str(scope.get('method', ''))
        parent = remote_parent(single_header(Headers(scope=scope), TRACEPARENT_HEADER))
        # 응답이 시작될 때의 상태 코드. 응답이 시작되기 전에 예외가 나면 비어 있다
        seen: dict[str, int] = {}

        async def send_watching(message: Message) -> None:
            if message['type'] == 'http.response.start':
                seen['status_code'] = message['status']
            await send(message)

        with tracer().start_as_current_span(
            method,
            context=parent,
            kind=SpanKind.SERVER,
            attributes={'http.request.method': method},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                await self.app(scope, receive, send_watching)
            except Exception:
                finish_server_span(span, scope, HTTPStatus.INTERNAL_SERVER_ERROR)
                raise
            finish_server_span(span, scope, seen.get('status_code', HTTPStatus.INTERNAL_SERVER_ERROR))
