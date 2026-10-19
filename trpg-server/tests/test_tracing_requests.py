# trpg-server/tests/test_tracing_requests.py

"""
요청마다 서버 span 이 걸리고 로그의 trace_id 가 그 span 의 것인지 검증한다(app/observability/request_spans.py).
span 은 메모리에 모은다(tests/spans.py). 규격은 docs/observability.md 의 "3. 추적"에 있다.
"""

import logging
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.main import API_PREFIX, create_app
from app.observability.spans import ATTRIBUTE_REQUEST_ID
from tests.logs import rendered
from tests.signing import FakeAuthServer
from tests.spans import SpanRecorder, hex_span_id, hex_trace_id

REQUEST_LOGGER = 'app.observability.middleware'
TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736'
PARENT_ID = '00f067aa0ba902b7'
TRACEPARENT = f'00-{TRACE_ID}-{PARENT_ID}-01'
THING_ID = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b'
SECRET_IN_ERROR = 'postgresql+asyncpg://game:super-secret@db.internal:5432/trpg'


@pytest.fixture
async def traced(settings: Settings, auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """경로에 값이 든 주소와 예외를 내는 주소가 붙은 앱의 클라이언트. 서버가 내보내는 500 을 그대로 받는다."""
    app = create_app(settings, http_client=auth_server.make_client(), engine=engine)

    @app.get(f'{API_PREFIX}/things/{{thing_id}}')
    async def thing(thing_id: str) -> dict:
        return {'ok': True}

    @app.get(f'{API_PREFIX}/broken')
    async def broken() -> None:
        raise RuntimeError(f'connect failed: {SECRET_IN_ERROR}')

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        yield client
    await app.state.http_client.aclose()


def finished_line(caplog: pytest.LogCaptureFixture) -> dict:
    """요청이 끝났다는 줄. 하나여야 한다."""
    (line,) = [line for line in rendered(caplog.records, REQUEST_LOGGER) if 'status_code' in line]
    return line


async def test_a_request_gets_a_server_span_named_by_its_route(traced: AsyncClient, spans: SpanRecorder):
    await traced.get(f'{API_PREFIX}/things/{THING_ID}?secret=query-value')

    span = spans.only()
    route = f'{API_PREFIX}/things/{{thing_id}}'
    assert span.name == f'GET {route}'
    assert span.kind == SpanKind.SERVER
    assert span.attributes['http.route'] == route
    assert span.attributes['http.request.method'] == 'GET'
    assert span.attributes['http.response.status_code'] == 200
    # 주소에 든 값과 주소 뒤의 값은 싣지 않는다
    assert THING_ID not in str(dict(span.attributes))
    assert 'query-value' not in str(dict(span.attributes))


async def test_the_log_trace_id_and_the_request_id_follow_the_span(
    traced: AsyncClient, spans: SpanRecorder, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.DEBUG, logger=REQUEST_LOGGER):
        response = await traced.get(f'{API_PREFIX}/things/{THING_ID}')

    span = spans.only()
    line = finished_line(caplog)
    # 로그에서 Tempo 로, Tempo 에서 로그로 같은 번호로 건너간다
    assert line['trace_id'] == hex_trace_id(span)
    # 응답의 X-Request-ID 로 Tempo 에서 그 요청을 찾는다
    assert span.attributes[ATTRIBUTE_REQUEST_ID] == response.headers['X-Request-ID']


async def test_the_callers_span_becomes_the_parent(traced: AsyncClient, spans: SpanRecorder):
    await traced.get(f'{API_PREFIX}/things/{THING_ID}', headers={'traceparent': TRACEPARENT})

    span = spans.only()
    assert hex_trace_id(span) == TRACE_ID
    assert span.parent is not None
    assert hex_span_id(span.parent.span_id) == PARENT_ID
    assert span.parent.is_remote


async def test_a_caller_that_does_not_record_is_still_recorded(traced: AsyncClient, spans: SpanRecorder):
    # span 을 내보내지 않는 서버는 flags 00 을 보낸다. 그것을 따르면 이 서버의 span 이 다 버려진다
    await traced.get(f'{API_PREFIX}/things/{THING_ID}', headers={'traceparent': f'00-{TRACE_ID}-{PARENT_ID}-00'})

    assert hex_trace_id(spans.only()) == TRACE_ID


@pytest.mark.parametrize(
    'value',
    [
        f'00-{TRACE_ID.upper()}-{PARENT_ID}-01',
        f'00-{"0" * 32}-{PARENT_ID}-01',
        f'01-{TRACE_ID}-{PARENT_ID}-01',
        'garbage',
    ],
)
async def test_a_malformed_traceparent_starts_a_new_trace(traced: AsyncClient, spans: SpanRecorder, value: str):
    await traced.get(f'{API_PREFIX}/things/{THING_ID}', headers={'traceparent': value})

    span = spans.only()
    assert span.parent is None
    assert hex_trace_id(span) != TRACE_ID


async def test_a_repeated_traceparent_starts_a_new_trace(traced: AsyncClient, spans: SpanRecorder):
    headers = [('traceparent', TRACEPARENT), ('traceparent', f'00-{TRACE_ID}-{PARENT_ID}-00')]

    await traced.get(f'{API_PREFIX}/things/{THING_ID}', headers=headers)

    assert spans.only().parent is None


async def test_probes_get_no_span(traced: AsyncClient, spans: SpanRecorder):
    # 10초마다 오는 확인이 추적을 메우지 않는다
    await traced.get('/health')
    await traced.get('/health/ready')

    assert spans.names() == []


async def test_a_server_error_marks_the_span_without_its_contents(traced: AsyncClient, spans: SpanRecorder):
    response = await traced.get(f'{API_PREFIX}/broken')

    span = spans.only()
    assert response.status_code == 500
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes['http.response.status_code'] == 500
    # 예외의 글은 싣지 않는다
    assert SECRET_IN_ERROR not in str(span.status.description)
    assert span.events == ()


async def test_an_unmatched_address_is_marked_but_not_an_error(traced: AsyncClient, spans: SpanRecorder):
    await traced.get(f'/no/such/address/{THING_ID}')

    span = spans.only()
    assert span.name == 'GET (unmatched)'
    assert span.status.status_code != StatusCode.ERROR
    assert THING_ID not in str(dict(span.attributes))


async def test_without_tracing_the_log_keeps_the_callers_trace(traced: AsyncClient, caplog: pytest.LogCaptureFixture):
    # span 을 내보내지 않으면(PC) 지금처럼 받은 traceparent 를 이어 쓴다
    with caplog.at_level(logging.DEBUG, logger=REQUEST_LOGGER):
        await traced.get(f'{API_PREFIX}/things/{THING_ID}', headers={'traceparent': TRACEPARENT})

    assert finished_line(caplog)['trace_id'] == TRACE_ID


async def test_a_table_stream_gets_no_span(traced: AsyncClient, spans: SpanRecorder):
    # 응답이 몇 시간씩 끝나지 않는다. 그동안의 쿼리가 한 span 아래에 쌓이지 않게 걸지 않는다
    await traced.get(f'{API_PREFIX}/tables/{THING_ID}/stream')

    assert spans.names() == []


async def test_other_addresses_under_a_table_still_get_a_span(traced: AsyncClient, spans: SpanRecorder):
    await traced.get(f'{API_PREFIX}/tables/{THING_ID}/stream/extra')
    await traced.get(f'{API_PREFIX}/tables/{THING_ID}')

    assert len(spans.names()) == 2
