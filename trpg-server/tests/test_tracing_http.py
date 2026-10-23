# trpg-server/tests/test_tracing_http.py

"""
다른 곳을 부르는 요청에 client span 이 걸리는지 검증한다(app/observability/http_spans.py).
상대는 httpx 의 가짜 transport 다. 실제로 보내지 않는다.

이 서버는 한 클라이언트로 우리 서버(인증, 결제, 알림)와 바깥(AI 모델의 창구)을 함께 부른다.
traceparent 는 부르는 쪽이 붙였을 때만(우리 서버) 이 span 으로 바꾼다. 붙이지 않은 바깥에는 붙이지 않는다.
"""

import httpx
import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanKind, StatusCode
from server_core.auth.jwks import fetch_jwks
from server_core.observability.context import outgoing_headers, request_scope
from server_core.observability.identifiers import Trace, parse_traceparent
from server_core.testing.tokens import FakeAuthServer

from app.observability.http_spans import TracingTransport, traced_client
from tests.spans import SpanRecorder, hex_span_id, hex_trace_id

JWKS_URL = 'http://auth.test/api/v1/auth/jwks'
MODEL_URL = 'https://api.example.test/v1/chat/completions'
# 주소에 든 값을 흉내 낸다. span 에 실리면 안 된다
SECRET_PATH = 'http://billing.test/api/v1/billing/holds/secret-hold-0b9f5e0c'
TRACE = Trace(trace_id='4bf92f3577b34da6a3ce929d0e0e4736', flags='01')


class Answering:
    """받은 요청을 적어 두고 status 로 답하는 가짜 상대."""

    def __init__(self, status: int = 200, fail: bool = False) -> None:
        self.status = status
        self.fail = fail
        self.received: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.received.append(request)
        if self.fail:
            raise httpx.ConnectError(f'{request.url} 에 닿지 못했다', request=request)
        return httpx.Response(self.status, json={})


def traceparent_of(span: ReadableSpan) -> str:
    """그 span 을 부모로 하는 traceparent. 표시(flags)는 SDK 가 정한 그대로다(기록함, 무작위 번호)."""
    return f'00-{hex_trace_id(span)}-{hex_span_id(span.context.span_id)}-{span.context.trace_flags:02x}'


def client_for(answering: Answering) -> httpx.AsyncClient:
    """client span 을 거는 클라이언트. 상대는 가짜다."""
    return httpx.AsyncClient(transport=TracingTransport(httpx.MockTransport(answering)))


async def test_a_call_under_a_span_gets_a_client_span(spans: SpanRecorder):
    async with client_for(Answering()) as client:
        with spans.parent() as parent:
            await client.post(SECRET_PATH, json={})

    span = spans.only()
    assert span.name == 'HTTP POST'
    assert span.kind == SpanKind.CLIENT
    assert span.parent.span_id == parent.get_span_context().span_id
    assert span.attributes['server.address'] == 'billing.test'
    assert span.attributes['http.response.status_code'] == 200
    assert span.status.status_code != StatusCode.ERROR
    # 주소의 경로는 싣지 않는다
    assert 'secret-hold' not in str(dict(span.attributes))


async def test_our_servers_receive_the_client_span_as_parent(spans: SpanRecorder):
    answering = Answering()

    async with client_for(answering) as client:
        with spans.parent():
            # 우리 서버를 부르는 쪽은 outgoing_headers 를 붙인다(app/billing/http_billing.py)
            await client.post(SECRET_PATH, json={}, headers=outgoing_headers())

    (request,) = answering.received
    assert request.headers['traceparent'] == traceparent_of(spans.only())


async def test_outside_services_receive_no_traceparent(spans: SpanRecorder):
    # AI 모델의 창구는 traceparent 를 붙이지 않고 부른다. 우리 안의 흐름을 밖에 알리지 않는다
    answering = Answering()

    async with client_for(answering) as client:
        with spans.parent():
            await client.post(MODEL_URL, json={})

    (request,) = answering.received
    assert 'traceparent' not in request.headers
    assert spans.only().attributes['server.address'] == 'api.example.test'


async def test_a_call_without_a_parent_gets_no_span(spans: SpanRecorder, auth_server: FakeAuthServer):
    # 요청이나 작업 밖에서 도는 호출(끊긴 세션의 목록을 받는 것)은 저마다 새 추적이 되어 Tempo 를 메운다
    received: list[httpx.Request] = []

    async def record(request: httpx.Request) -> None:
        received.append(request)

    client = httpx.AsyncClient(
        transport=TracingTransport(httpx.MockTransport(auth_server.handle)), event_hooks={'request': [record]}
    )
    async with client:
        with request_scope('request-12345', TRACE):
            await fetch_jwks(client, JWKS_URL)

    assert spans.names() == []
    # span 이 없어도 추적은 지금처럼 잇는다
    assert parse_traceparent(received[0].headers['traceparent']) == TRACE


async def test_the_auth_server_call_inside_a_span_names_it_as_parent(spans: SpanRecorder, auth_server: FakeAuthServer):
    sent: list[str] = []

    async def record(response: httpx.Response) -> None:
        sent.append(response.request.headers['traceparent'])

    client = httpx.AsyncClient(
        transport=TracingTransport(httpx.MockTransport(auth_server.handle)), event_hooks={'response': [record]}
    )
    async with client:
        with spans.parent(), request_scope('request-12345', TRACE):
            await fetch_jwks(client, JWKS_URL)

    assert sent == [traceparent_of(spans.only())]


@pytest.mark.parametrize(('status', 'marked'), [(503, True), (500, True), (404, False), (402, False)])
async def test_only_server_errors_mark_the_span(spans: SpanRecorder, status: int, marked: bool):
    async with client_for(Answering(status=status)) as client:
        with spans.parent():
            await client.get(JWKS_URL)

    assert (spans.only().status.status_code == StatusCode.ERROR) is marked


async def test_an_unreachable_server_marks_the_span_without_the_address(spans: SpanRecorder):
    async with client_for(Answering(fail=True)) as client:
        with spans.parent(), pytest.raises(httpx.ConnectError):
            await client.get(SECRET_PATH)

    span = spans.only()
    assert span.status.status_code == StatusCode.ERROR
    assert 'secret-hold' not in str(span.status.description)
    assert span.events == ()


async def test_the_default_client_traces_and_closes():
    client = traced_client()

    assert isinstance(client._transport, TracingTransport)
    await client.aclose()
