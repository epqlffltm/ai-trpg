# asset-server/app/observability/http_spans.py

"""
다른 곳을 부르는 HTTP 요청에 client span 을 거는 httpx 의 transport. 인증 서버를 부르는 클라이언트에 단다(app/main.py).

span 에는 메서드, 상대의 호스트 이름, 상태 코드만 싣는다. 주소의 경로와 뒤의 값, 머리말, 본문은 싣지 않는다.
부모 span 이 기록 중일 때만 건다. 요청이나 작업 밖에서 도는 호출(끊긴 세션의 목록을 30초마다 받는 것)은
저마다 새 추적이 되어 Tempo 를 메운다.

propagate 면 우리 서버끼리의 요청이라 traceparent 를 이 span 으로 바꿔 붙인다.
받는 서버의 span 이 이 span 아래에 붙는다.
부르는 쪽(app/auth/jwks.py)이 붙인 traceparent(outgoing_headers)는 span 이 없을 때 그대로 간다.
"""

import httpx
from opentelemetry.trace import Span, SpanKind, StatusCode

from app.observability.identifiers import TRACEPARENT_HEADER
from app.observability.spans import is_recording, span_traceparent, tracer

# client span 의 이름 앞부분. 메서드만 붙인다(HTTP GET). 주소는 값의 종류가 끝없이 늘어 이름에 넣지 않는다
SPAN_NAME_PREFIX = 'HTTP '
# 서버의 잘못으로 보는 상태 코드의 시작
SERVER_ERROR = 500


def record_response(span: Span, response: httpx.Response) -> None:
    """답을 span 에 적는다. 상대의 잘못(5xx)만 오류로 표시한다. 4xx 는 부른 쪽이 답을 보고 다룬다."""
    span.set_attribute('http.response.status_code', response.status_code)
    if response.status_code >= SERVER_ERROR:
        span.set_status(StatusCode.ERROR, response.reason_phrase)


def propagate_span(request: httpx.Request) -> None:
    """요청의 traceparent 를 지금의 span 으로 바꾼다. 받는 서버의 span 이 그 아래에 붙는다."""
    traceparent = span_traceparent()
    if traceparent is not None:
        request.headers[TRACEPARENT_HEADER] = traceparent


class TracingTransport(httpx.AsyncBaseTransport):
    """inner 를 감싸 요청마다 client span 을 거는 transport."""

    def __init__(self, inner: httpx.AsyncBaseTransport, propagate: bool) -> None:
        self.inner = inner
        self.propagate = propagate

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """요청 하나를 보낸다. 부모 span 이 없으면 span 없이 보낸다."""
        if not is_recording():
            return await self.inner.handle_async_request(request)
        with tracer().start_as_current_span(
            SPAN_NAME_PREFIX + request.method,
            kind=SpanKind.CLIENT,
            attributes={'http.request.method': request.method, 'server.address': request.url.host},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            if self.propagate:
                propagate_span(request)
            try:
                response = await self.inner.handle_async_request(request)
            except Exception:
                # 오류의 글은 싣지 않는다. 주소가 들어 있을 수 있다
                span.set_status(StatusCode.ERROR, '요청을 보내지 못했다')
                raise
            record_response(span, response)
            return response

    async def aclose(self) -> None:
        """감싼 transport 의 연결을 닫는다."""
        await self.inner.aclose()


def traced_client(propagate: bool = True) -> httpx.AsyncClient:
    """
    client span 을 거는 클라이언트. 이 서버가 부르는 곳은 인증 서버(우리 서버)뿐이라 기본으로 traceparent 를 잇는다.
    """
    return httpx.AsyncClient(transport=TracingTransport(httpx.AsyncHTTPTransport(), propagate=propagate))
