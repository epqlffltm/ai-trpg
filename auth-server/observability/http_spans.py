# auth-server/observability/http_spans.py

"""
다른 서버를 부르는 요청에 client span 을 건다. 결제 서버를 부르는 곳(accounts/billing_client.py)이 쓴다.

이 서버는 표준 라이브러리(urllib)로 부른다. 그래서 transport 를 감싸지 않고, 부르는 곳이 이 span 안에서
머리말을 만들고 보낸다. 그러면 outgoing_headers() 가 붙이는 traceparent 가 이 span 을 부모로 가리킨다.

span 에는 메서드, 상대의 호스트 이름, 상태 코드만 싣는다. 주소의 경로, 머리말, 본문은 싣지 않는다.
부모 span 이 기록 중일 때만 건다(요청이나 작업 안의 호출). 아니면 None 을 내주고 아무것도 하지 않는다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from http import HTTPStatus
from urllib.parse import urlsplit

from opentelemetry.trace import Span, SpanKind, StatusCode

from observability.spans import is_recording, tracer

# client span 의 이름 앞부분. 메서드만 붙인다(HTTP POST)
SPAN_NAME_PREFIX = 'HTTP '


@contextmanager
def client_span(method: str, url: str) -> Iterator[Span | None]:
    """
    다른 서버를 부르는 동안 건 client span. 부모 span 이 없으면 None 이다.

    예외의 글은 싣지 않는다. 주소가 들어 있을 수 있다. 상태는 부르는 쪽이 record_status, mark_unreachable 로 적는다.
    """
    if not is_recording():
        yield None
        return
    with tracer().start_as_current_span(
        SPAN_NAME_PREFIX + method,
        kind=SpanKind.CLIENT,
        attributes={'http.request.method': method, 'server.address': urlsplit(url).hostname or ''},
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        yield span


def record_status(span: Span | None, status_code: int) -> None:
    """받은 상태 코드를 적는다. 상대의 잘못(5xx)만 오류로 표시한다. 4xx 는 부른 쪽이 답을 보고 다룬다."""
    if span is None:
        return
    span.set_attribute('http.response.status_code', status_code)
    if status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        span.set_status(StatusCode.ERROR, HTTPStatus(status_code).phrase)


def mark_unreachable(span: Span | None) -> None:
    """닿지 못했다(연결 실패, 시간 초과)고 적는다."""
    if span is not None:
        span.set_status(StatusCode.ERROR, '요청을 보내지 못했다')
