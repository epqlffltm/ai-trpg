# game-server/tests/test_observability_requests.py

"""
요청마다 식별자가 걸리고 끝나면 한 줄이 남는지 검증한다(app/observability/middleware.py).
앱을 통째로 만들어 요청을 보내고, 응답의 머리말과 남은 로그를 본다. 규격은 docs/observability.md 에 있다.
"""

import logging
import re
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import API_PREFIX, create_app
from app.observability.middleware import level_of
from tests.logs import rendered
from tests.signing import FakeAuthServer, SigningKey, make_access_claims, make_token

REQUEST_LOGGER = 'app.observability.middleware'
TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736'
TRACEPARENT = f'00-{TRACE_ID}-00f067aa0ba902b7-01'
# 서명까지 갖춘 토큰의 모양. 실제 키로 만든 것이 아니다
FAKE_TOKEN = 'eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVlLWhlcmU'
# 예외의 글에 든, 응답에 실리면 안 되는 값
SECRET_IN_ERROR = 'postgresql+asyncpg://game:super-secret@db.internal:5432/trpg'


def request_lines(caplog: pytest.LogCaptureFixture) -> list[dict]:
    """요청 식별 미들웨어가 남긴 줄들."""
    return rendered(caplog.records, REQUEST_LOGGER)


def finished_line(caplog: pytest.LogCaptureFixture) -> dict:
    """요청이 끝났다는 줄. 하나여야 한다."""
    (line,) = [line for line in request_lines(caplog) if 'status_code' in line]
    return line


@pytest.fixture
async def broken_client(settings: Settings, auth_server: FakeAuthServer) -> AsyncIterator[AsyncClient]:
    """
    처리하지 못한 예외를 내는 주소가 하나 붙은 앱의 클라이언트.

    예외를 테스트로 올리지 않고 서버가 내보내는 500 응답을 그대로 받는다(raise_app_exceptions=False).
    """
    app = create_app(settings, http_client=auth_server.make_client())

    @app.get(f'{API_PREFIX}/broken/{{thing_id}}')
    async def broken(thing_id: str) -> None:
        raise RuntimeError(f'connect failed: {SECRET_IN_ERROR}')

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        yield client
    await app.state.jobs.aclose()
    await app.state.signal_source.stop()
    await app.state.engine.dispose()
    await app.state.http_client.aclose()


async def test_a_request_without_an_id_gets_a_new_one(client: AsyncClient):
    response = await client.get('/health')

    request_id = response.headers['X-Request-ID']
    assert str(uuid.UUID(request_id)) == request_id


async def test_every_request_gets_a_different_id(client: AsyncClient):
    first = await client.get('/health')
    second = await client.get('/health')

    assert first.headers['X-Request-ID'] != second.headers['X-Request-ID']


async def test_a_well_formed_id_is_kept(client: AsyncClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.DEBUG, logger=REQUEST_LOGGER):
        response = await client.get('/health', headers={'X-Request-ID': 'client-chosen-id-0001'})

    assert response.headers['X-Request-ID'] == 'client-chosen-id-0001'
    assert finished_line(caplog)['request_id'] == 'client-chosen-id-0001'


@pytest.mark.parametrize(
    'value',
    ['short', 'a' * 65, 'a' * 3000, 'has space in it', '{"level":"error"}', 'semi;colon-12345', '한글-식별자-12345'],
)
async def test_a_malformed_id_is_replaced(client: AsyncClient, caplog: pytest.LogCaptureFixture, value: str):
    with caplog.at_level(logging.DEBUG, logger=REQUEST_LOGGER):
        response = await client.get('/health', headers={b'X-Request-ID': value.encode()})

    request_id = response.headers['X-Request-ID']
    assert str(uuid.UUID(request_id)) == request_id
    # 받은 값은 응답에도 로그에도 남지 않는다
    assert value not in str(request_lines(caplog))


async def test_a_repeated_id_header_is_replaced(client: AsyncClient):
    headers = [('X-Request-ID', 'client-chosen-id-0001'), ('X-Request-ID', 'client-chosen-id-0002')]

    response = await client.get('/health', headers=headers)

    # 어느 것을 믿을지 정할 수 없다. 둘 다 버린다
    request_id = response.headers['X-Request-ID']
    assert str(uuid.UUID(request_id)) == request_id


async def test_control_characters_in_the_id_never_reach_the_log(caplog: pytest.LogCaptureFixture, app: FastAPI):
    # 줄바꿈이 든 머리말은 HTTP 클라이언트가 보내 주지 않는다. 미들웨어에 요청을 직접 넘긴다
    injected = b'request-12345\r\n{"level":"error","message":"forged"}'
    sent: list[dict] = []

    async def receive() -> dict:
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': 'GET',
        'scheme': 'http',
        'path': '/health',
        'raw_path': b'/health',
        'query_string': b'',
        'root_path': '',
        'headers': [(b'x-request-id', injected), (b'traceparent', TRACEPARENT.encode() + b'\nforged')],
        'client': ('127.0.0.1', 1234),
        'server': ('testserver', 80),
    }
    with caplog.at_level(logging.DEBUG, logger=REQUEST_LOGGER):
        await app(scope, receive, send)

    line = finished_line(caplog)
    assert str(uuid.UUID(line['request_id'])) == line['request_id']
    assert line['trace_id'] != TRACE_ID
    assert 'forged' not in str(line)
    response_headers = dict(sent[0]['headers'])
    assert response_headers[b'x-request-id'].decode() == line['request_id']


async def test_the_finished_line_has_the_common_fields(
    client: AsyncClient, caplog: pytest.LogCaptureFixture, signing_key: SigningKey
):
    # 상태 확인 주소가 아닌 보통의 주소로 본다. 상태 확인의 줄은 수준이 다르다(아래)
    headers = {'Authorization': f'Bearer {make_token(signing_key, make_access_claims())}'}

    with caplog.at_level(logging.INFO, logger=REQUEST_LOGGER):
        response = await client.get(f'{API_PREFIX}/me', headers=headers)

    line = finished_line(caplog)
    for field in ('timestamp', 'level', 'service', 'environment', 'version', 'request_id', 'trace_id'):
        assert line[field], field
    assert line['operation'] == 'http.request'
    assert line['method'] == 'GET'
    assert line['route'] == f'{API_PREFIX}/me'
    assert line['status_code'] == status.HTTP_200_OK
    assert line['result'] == 'success'
    assert line['level'] == 'info'
    assert isinstance(line['duration_ms'], int)
    assert line['request_id'] == response.headers['X-Request-ID']
    assert re.fullmatch(r'[0-9a-f]{32}', line['trace_id'])


async def test_the_trace_is_carried_on_from_the_caller(client: AsyncClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.DEBUG, logger=REQUEST_LOGGER):
        await client.get('/health', headers={'traceparent': TRACEPARENT})

    assert finished_line(caplog)['trace_id'] == TRACE_ID


async def test_the_route_is_logged_as_a_template_not_the_real_path(
    client: AsyncClient, caplog: pytest.LogCaptureFixture, signing_key: SigningKey
):
    table_id = uuid.uuid4()
    headers = {'Authorization': f'Bearer {make_token(signing_key, make_access_claims())}'}

    with caplog.at_level(logging.INFO, logger=REQUEST_LOGGER):
        response = await client.get(f'{API_PREFIX}/tables/{table_id}?secret=query-value', headers=headers)

    line = finished_line(caplog)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert line['route'] == f'{API_PREFIX}/tables/{{table_id}}'
    # 주소에 든 ID 와 주소 뒤에 붙인 값은 남지 않는다
    assert str(table_id) not in str(line)
    assert 'query-value' not in str(line)


async def test_a_client_error_is_info_and_marked_as_the_clients(client: AsyncClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=REQUEST_LOGGER):
        response = await client.get(f'{API_PREFIX}/me')

    line = finished_line(caplog)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert line['status_code'] == status.HTTP_401_UNAUTHORIZED
    assert line['result'] == 'client_error'
    # 요청이 틀린 것이다. 서버는 제 일을 했다. 경고로 올리지 않는다
    assert line['level'] == 'info'


async def test_an_unknown_address_logs_the_real_path_separately(client: AsyncClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=REQUEST_LOGGER):
        response = await client.get('/no/such/address')

    line = finished_line(caplog)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    # 맞는 틀이 없다. 틀 자리에 실제 주소를 넣지 않는다
    assert line['route'] == '(unmatched)'
    assert line['path'] == '/no/such/address'


async def test_the_token_and_cookie_never_reach_the_log(client: AsyncClient, caplog: pytest.LogCaptureFixture):
    headers = {'Authorization': f'Bearer {FAKE_TOKEN}', 'Cookie': 'refresh_token=cookie-secret-value'}

    with caplog.at_level(logging.DEBUG):
        await client.get(f'{API_PREFIX}/me', headers=headers)

    everything = str([line for record in caplog.records for line in rendered([record], record.name)])
    assert FAKE_TOKEN not in everything
    assert 'cookie-secret-value' not in everything
    assert 'Bearer' not in everything


async def test_an_unhandled_exception_is_logged_with_the_request_id(
    broken_client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.INFO, logger=REQUEST_LOGGER):
        response = await broken_client.get(f'{API_PREFIX}/broken/thing-1234', headers={'traceparent': TRACEPARENT})

    request_id = response.headers['X-Request-ID']
    (error_line,) = [line for line in request_lines(caplog) if 'stack_trace' in line]
    assert error_line['level'] == 'error'
    assert error_line['request_id'] == request_id
    assert error_line['trace_id'] == TRACE_ID
    assert error_line['operation'] == 'http.request'
    assert error_line['error_code'] == 'http.unhandled_exception'
    assert error_line['error_type'] == 'RuntimeError'
    assert error_line['route'] == f'{API_PREFIX}/broken/{{thing_id}}'
    assert 'RuntimeError' in error_line['stack_trace']
    # 예외의 글에 든 비밀번호는 로그에서도 가려진다
    assert 'super-secret' not in str(error_line)


async def test_a_server_error_is_logged_as_an_error(broken_client: AsyncClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=REQUEST_LOGGER):
        await broken_client.get(f'{API_PREFIX}/broken/thing-1234')

    line = finished_line(caplog)
    assert line['status_code'] == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert line['result'] == 'server_error'
    assert line['level'] == 'error'


async def test_the_500_response_does_not_reveal_the_exception(broken_client: AsyncClient):
    response = await broken_client.get(f'{API_PREFIX}/broken/thing-1234')

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {'detail': '서버에서 오류가 났습니다. 잠시 후 다시 시도해 주세요.'}
    assert 'super-secret' not in response.text
    assert 'RuntimeError' not in response.text
    assert 'Traceback' not in response.text
    # 문제를 알릴 때 쓸 식별자는 돌려준다
    assert response.headers['X-Request-ID']


async def test_health_and_readiness_keep_their_shape(client: AsyncClient):
    health = await client.get('/health')
    ready = await client.get('/health/ready')

    # 식별자는 머리말로만 돌려준다. 본문의 모양은 그대로다
    assert health.json() == {'status': 'ok'}
    assert ready.json() == {'status': 'ok'}


@pytest.mark.parametrize('url', ['/health', '/health/ready'])
async def test_a_successful_probe_is_debug(client: AsyncClient, caplog: pytest.LogCaptureFixture, url: str):
    with caplog.at_level(logging.DEBUG, logger=REQUEST_LOGGER):
        await client.get(url)

    # 관리 도구가 10초마다 부른다. 운영의 수준(info)에서는 남지 않는다
    line = finished_line(caplog)
    assert (line['level'], line['route']) == ('debug', url)


async def test_a_successful_probe_is_not_written_at_info(client: AsyncClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=REQUEST_LOGGER):
        await client.get('/health')

    assert request_lines(caplog) == []


@pytest.mark.parametrize(
    ('status_code', 'level'),
    [(200, logging.DEBUG), (404, logging.DEBUG), (503, logging.WARNING), (500, logging.ERROR)],
)
def test_the_level_of_a_probe(status_code: int, level: int):
    # 503 은 이 주소의 답이다(준비 안 됨). 서버의 잘못(error)이 아니다. 패닉 같은 다른 5xx 는 error 다
    assert level_of('/health/ready', status_code) == level


def test_other_routes_keep_their_level():
    assert level_of(f'{API_PREFIX}/me', 503) == logging.ERROR
    assert level_of(f'{API_PREFIX}/me', 200) == logging.INFO
