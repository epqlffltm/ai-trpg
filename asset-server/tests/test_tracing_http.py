# asset-server/tests/test_tracing_http.py

"""
다른 곳을 부르는 요청에 client span 이 걸리는지 검증한다(app/observability/http_spans.py).
상대는 httpx 의 가짜 transport 다. 실제로 보내지 않는다.
"""

import httpx
import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanKind, StatusCode

from app.auth.jwks import fetch_jwks
from app.observability.context import request_scope
from app.observability.http_spans import TracingTransport, traced_client
from app.observability.identifiers import Trace, parse_traceparent
from tests.spans import SpanRecorder, hex_span_id, hex_trace_id
from tests.tokens import FakeAuthServer

JWKS_URL = 'http://auth.test/api/v1/auth/jwks'
# 주소에 든 값을 흉내 낸다. span 에 실리면 안 된다
SECRET_PATH = 'http://auth.test/api/v1/auth/users/secret-user-0b9f5e0c'
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


def client_for(answering: Answering, propagate: bool = True) -> httpx.AsyncClient:
    """client span 을 거는 클라이언트. 상대는 가짜다."""
    return httpx.AsyncClient(transport=TracingTransport(httpx.MockTransport(answering), propagate=propagate))


async def test_a_call_under_a_span_gets_a_client_span(spans: SpanRecorder):
    answering = Answering()

    async with client_for(answering) as client:
        with spans.parent() as parent:
            await client.get(SECRET_PATH)

    span = spans.only()
    assert span.name == 'HTTP GET'
    assert span.kind == SpanKind.CLIENT
    assert span.parent.span_id == parent.get_span_context().span_id
    assert span.attributes['server.address'] == 'auth.test'
    assert span.attributes['http.response.status_code'] == 200
    assert span.status.status_code != StatusCode.ERROR
    # 주소의 경로는 싣지 않는다
    assert 'secret-user' not in str(dict(span.attributes))


async def test_our_servers_receive_the_client_span_as_parent(spans: SpanRecorder):
    answering = Answering()

    async with client_for(answering) as client:
        with spans.parent():
            await client.get(JWKS_URL, headers={'traceparent': '00-' + '1' * 32 + '-' + '2' * 16 + '-00'})

    span = spans.only()
    (request,) = answering.received
    assert request.headers['traceparent'] == traceparent_of(span)


async def test_outside_servers_keep_what_the_caller_sent(spans: SpanRecorder):
    answering = Answering()

    async with client_for(answering, propagate=False) as client:
        with spans.parent():
            await client.get(JWKS_URL)

    (request,) = answering.received
    assert 'traceparent' not in request.headers
    assert spans.names() == ['HTTP GET']


async def test_a_call_without_a_parent_gets_no_span(spans: SpanRecorder, auth_server: FakeAuthServer):
    # 요청이나 작업 밖에서 도는 호출(끊긴 세션의 목록을 받는 것)은 저마다 새 추적이 되어 Tempo 를 메운다
    received: list[httpx.Request] = []

    async def record(request: httpx.Request) -> None:
        received.append(request)

    client = httpx.AsyncClient(
        transport=TracingTransport(httpx.MockTransport(auth_server.handle), propagate=True),
        event_hooks={'request': [record]},
    )
    async with client:
        with request_scope('request-12345', TRACE):
            await fetch_jwks(client, JWKS_URL)

    assert spans.names() == []
    # span 이 없어도 추적은 지금처럼 잇는다
    assert parse_traceparent(received[0].headers['traceparent']) == TRACE


async def test_the_auth_server_call_inside_a_span_names_it_as_parent(spans: SpanRecorder, auth_server: FakeAuthServer):
    client = httpx.AsyncClient(transport=TracingTransport(httpx.MockTransport(auth_server.handle), propagate=True))
    sent: list[str] = []

    async def record(request: httpx.Request) -> None:
        sent.append(request.headers['traceparent'])

    client.event_hooks['response'].append(lambda response: record(response.request))
    async with client:
        with spans.parent(), request_scope('request-12345', TRACE):
            await fetch_jwks(client, JWKS_URL)

    span = spans.only()
    assert sent == [traceparent_of(span)]


@pytest.mark.parametrize(('status', 'marked'), [(503, True), (500, True), (404, False), (401, False)])
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
    assert 'secret-user' not in str(span.status.description)
    assert span.events == ()


async def test_the_default_client_traces_and_closes():
    client = traced_client()

    assert isinstance(client._transport, TracingTransport)
    assert client._transport.propagate
    await client.aclose()
