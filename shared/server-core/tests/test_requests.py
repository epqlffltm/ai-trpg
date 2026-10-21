# shared/server-core/tests/test_requests.py

"""
요청을 지나가는 관측을 작은 앱으로 검증한다. 서버의 app/main.py 와 같은 차례로 미들웨어 셋과 예외 처리기를 단다.

  - 로그(server_core/observability/middleware.py): 요청의 식별자, 끝난 줄, 경로의 틀, 처리하지 못한 예외
  - 500 응답(responses.py): 예외의 글을 드러내지 않고 요청의 식별자를 돌려준다
  - 추적(request_spans.py): 받은 traceparent 를 부모로, 상태 확인은 걸지 않는다
  - 메트릭(request_metrics.py): 방법, 경로의 틀, 상태 코드로 센다

서버의 주소(상태 확인, DB 를 보는 readiness)를 지나가는 것은 그 서버의 테스트가 본다.
"""

import logging
from collections.abc import AsyncIterator

import pytest
from fastapi import APIRouter, FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient
from opentelemetry.trace import StatusCode

from server_core.observability.identifiers import REQUEST_ID_HEADER
from server_core.observability.middleware import (
    HTTP_OPERATION,
    UNHANDLED_ERROR_CODE,
    UNMATCHED_ROUTE,
    RequestLoggingMiddleware,
    level_of,
    result_of,
)
from server_core.observability.request_metrics import RequestMetricsMiddleware
from server_core.observability.request_spans import RequestSpanMiddleware
from server_core.observability.responses import SERVER_ERROR_DETAIL, handle_unexpected_error
from server_core.testing.logs import rendered
from server_core.testing.metrics import MetricsRecorder
from server_core.testing.spans import SpanRecorder

LOGGER = 'server_core.observability.middleware'
PREFIX = '/api/v1/test'
ITEM_ROUTE = f'{PREFIX}/items/{{item_id}}'
TRACE_ID = '0af7651916cd43dd8448eb211c80319c'
TRACEPARENT = f'00-{TRACE_ID}-b7ad6b7169203331-01'


async def health() -> dict:
    return {'status': 'ok'}


async def read_item(item_id: int) -> dict:
    if item_id == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='없다')
    return {'item_id': item_id}


async def broken(name: str) -> None:
    raise RuntimeError(f'connect failed: postgres://core:super-secret@db/trpg {name}')


def observed_app() -> FastAPI:
    """서버의 app/main.py 와 같은 차례로 관측을 단 앱. 나중에 붙인 미들웨어가 바깥이다."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestSpanMiddleware)
    app.add_middleware(RequestMetricsMiddleware)
    app.add_api_route('/health', health, methods=['GET'], status_code=status.HTTP_200_OK)
    router = APIRouter()
    router.add_api_route('/items/{item_id}', read_item, methods=['GET'], status_code=status.HTTP_200_OK)
    router.add_api_route('/broken/{name}', broken, methods=['GET'], status_code=status.HTTP_200_OK)
    app.include_router(router, prefix=PREFIX)
    app.add_exception_handler(Exception, handle_unexpected_error)
    return app


@pytest.fixture
async def observed() -> AsyncIterator[AsyncClient]:
    """관측을 단 앱에 요청을 보내는 클라이언트. 처리하지 못한 예외를 다시 올리지 않고 500 으로 받는다."""
    transport = ASGITransport(app=observed_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        yield client


def finished_lines(caplog: pytest.LogCaptureFixture) -> list[dict]:
    return [line for line in rendered(caplog.records, LOGGER) if line.get('operation') == HTTP_OPERATION]


# --- 로그 ---


async def test_a_request_gets_an_id_and_a_finished_line(observed: AsyncClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        response = await observed.get(f'{PREFIX}/items/42?secret=query-value')

    request_id = response.headers[REQUEST_ID_HEADER]
    (line,) = finished_lines(caplog)
    assert line['request_id'] == request_id
    assert line['method'] == 'GET'
    # 경로는 틀로 적는다. 실제 값과 주소 뒤의 값은 적지 않는다
    assert line['route'] == ITEM_ROUTE
    assert 'path' not in line
    assert 'query-value' not in str(line)
    assert line['status_code'] == 200
    assert line['result'] == 'success'
    assert isinstance(line['duration_ms'], int)


async def test_a_well_formed_id_is_kept_and_a_repeated_one_is_replaced(observed: AsyncClient):
    kept = await observed.get('/health', headers={REQUEST_ID_HEADER: 'client-chosen-id-0001'})
    repeated = await observed.get(
        '/health', headers=[(REQUEST_ID_HEADER, 'aaaaaaaa1'), (REQUEST_ID_HEADER, 'bbbbbbbb2')]
    )

    assert kept.headers[REQUEST_ID_HEADER] == 'client-chosen-id-0001'
    assert repeated.headers[REQUEST_ID_HEADER] not in {'aaaaaaaa1', 'bbbbbbbb2'}


async def test_the_callers_trace_is_carried_on(observed: AsyncClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        await observed.get(f'{PREFIX}/items/1', headers={'traceparent': TRACEPARENT})

    (line,) = finished_lines(caplog)
    assert line['trace_id'] == TRACE_ID


async def test_a_client_error_is_info_and_an_unknown_address_logs_its_path(
    observed: AsyncClient, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        await observed.get(f'{PREFIX}/items/0')
        await observed.get('/no/such/address')

    missing, unknown = finished_lines(caplog)
    assert (missing['level'], missing['result'], missing['route']) == ('info', 'client_error', ITEM_ROUTE)
    assert (unknown['route'], unknown['path']) == (UNMATCHED_ROUTE, '/no/such/address')


async def test_an_unhandled_exception_is_logged_and_hidden_from_the_response(
    observed: AsyncClient, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        response = await observed.get(f'{PREFIX}/broken/thing-1234')

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {'detail': SERVER_ERROR_DETAIL}
    assert 'super-secret' not in response.text
    request_id = response.headers[REQUEST_ID_HEADER]
    unhandled, finished = rendered(caplog.records, LOGGER)
    assert unhandled['error_code'] == UNHANDLED_ERROR_CODE
    assert unhandled['request_id'] == request_id
    assert unhandled['route'] == f'{PREFIX}/broken/{{name}}'
    assert 'super-secret' not in unhandled['stack_trace']
    assert (finished['level'], finished['status_code'], finished['result']) == ('error', 500, 'server_error')


async def test_a_successful_probe_is_debug(observed: AsyncClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await observed.get('/health')

    (line,) = finished_lines(caplog)
    assert line['level'] == 'debug'


@pytest.mark.parametrize(
    ('route', 'status_code', 'level'),
    [
        ('/health/ready', 200, logging.DEBUG),
        ('/health/ready', 503, logging.WARNING),
        ('/health', 500, logging.ERROR),
        (ITEM_ROUTE, 404, logging.INFO),
        (ITEM_ROUTE, 502, logging.ERROR),
    ],
)
def test_the_level_of_a_finished_line(route: str, status_code: int, level: int):
    assert level_of(route, status_code) == level


@pytest.mark.parametrize(('status_code', 'result'), [(200, 'success'), (302, 'success'), (409, 'client_error')])
def test_the_result_of_a_status(status_code: int, result: str):
    assert result_of(status_code) == result


async def test_a_scope_that_is_not_http_is_passed_through():
    seen: list[dict] = []

    async def inner(scope, receive, send) -> None:
        seen.append(scope)

    await RequestLoggingMiddleware(inner)({'type': 'lifespan'}, None, None)
    await RequestMetricsMiddleware(inner)({'type': 'lifespan'}, None, None)

    assert seen == [{'type': 'lifespan'}, {'type': 'lifespan'}]


# --- 추적 ---


async def test_a_request_gets_a_server_span_under_the_callers_span(observed: AsyncClient, spans: SpanRecorder):
    response = await observed.get(f'{PREFIX}/items/7', headers={'traceparent': TRACEPARENT})

    span = spans.only()
    assert span.name == f'GET {ITEM_ROUTE}'
    assert span.attributes['http.route'] == ITEM_ROUTE
    assert span.attributes['http.response.status_code'] == 200
    assert span.attributes['request_id'] == response.headers[REQUEST_ID_HEADER]
    assert f'{span.context.trace_id:032x}' == TRACE_ID


async def test_probes_get_no_span(observed: AsyncClient, spans: SpanRecorder):
    await observed.get('/health')

    assert spans.ended() == []


async def test_a_server_error_marks_the_span_without_its_contents(observed: AsyncClient, spans: SpanRecorder):
    await observed.get(f'{PREFIX}/broken/thing-1234')

    span = spans.only()
    assert span.status.status_code == StatusCode.ERROR
    assert 'super-secret' not in str(span.status.description)
    assert span.events == ()


# --- 메트릭 ---


async def test_a_request_is_counted_by_method_route_and_status(observed: AsyncClient, metrics: MetricsRecorder):
    await observed.get(f'{PREFIX}/items/3')
    await observed.get(f'{PREFIX}/items/0')
    await observed.get(f'{PREFIX}/broken/x')

    labels = {'method': 'GET', 'route': ITEM_ROUTE}
    assert metrics.value('http_server_requests', **labels, status_code=200) == 1
    assert metrics.value('http_server_requests', **labels, status_code=404) == 1
    assert metrics.value('http_server_requests', status_code=500) == 1
    assert metrics.value('http_server_request_duration', **labels) == 2
    assert metrics.value('http_server_active_requests') == 0
