# notification-server/tests/test_tracing_setup.py

"""
span 을 OTLP(HTTP)로 미는 것(app/observability/tracing.py)과 그 설정(OTEL_EXPORTER_OTLP_ENDPOINT)을 검증한다.
수집기 대신 이 테스트의 HTTP 서버가 받는다.
"""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from pydantic import ValidationError

from app.core.database import create_engine
from app.main import create_app
from app.observability.request_spans import RequestSpanMiddleware
from app.observability.spans import tracer, use_provider
from app.observability.tracing import build_provider, configure_tracing, shutdown_tracing
from tests.conftest import make_client, make_test_settings
from tests.tokens import FakeAuthServer


class Collector:
    """OTLP 로 온 span 을 모으는 가짜 수집기. 따로 도는 스레드에서 받는다."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        self.requests: list[ExportTraceServiceRequest] = []
        self.lock = threading.Lock()

    def handler(self) -> type[BaseHTTPRequestHandler]:
        collector = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers['Content-Length']))
                request = ExportTraceServiceRequest()
                request.ParseFromString(body)
                with collector.lock:
                    collector.paths.append(self.path)
                    collector.requests.append(request)
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-protobuf')
                self.end_headers()

            def log_message(self, *_args: object) -> None:
                return

        return Handler

    def span_names(self) -> list[str]:
        """받은 span 의 이름들."""
        with self.lock:
            return [
                span.name
                for request in self.requests
                for resource in request.resource_spans
                for scope in resource.scope_spans
                for span in scope.spans
            ]

    def resource(self) -> dict[str, str]:
        """처음 받은 span 의 출처."""
        with self.lock:
            attributes = self.requests[0].resource_spans[0].resource.attributes
        return {attribute.key: attribute.value.string_value for attribute in attributes}


@pytest.fixture
def collector() -> Iterator[tuple[Collector, str]]:
    """가짜 수집기와 그 주소(경로 없이)."""
    received = Collector()
    server = HTTPServer(('127.0.0.1', 0), received.handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield received, f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()


@pytest.fixture
def restore_provider() -> Iterator[None]:
    """끼운 TracerProvider 를 테스트가 끝나면 아무것도 하지 않는 것으로 되돌린다."""
    yield
    use_provider(trace.NoOpTracerProvider())


@pytest.mark.parametrize(
    ('written', 'read'),
    [('', ''), ('  ', ''), ('http://alloy:4318', 'http://alloy:4318'), ('https://a.b:4318/', 'https://a.b:4318')],
)
def test_the_endpoint_is_read_without_a_path(written: str, read: str):
    assert make_test_settings(otel_exporter_otlp_endpoint=written).otel_exporter_otlp_endpoint == read


@pytest.mark.parametrize(
    'written',
    [
        'http://marked-host:4318/v1/traces',
        'marked-host:4318',
        'ftp://marked-host:4318',
        'http://marked-host:4318?x=1',
        'http://marked-host:4318#x',
        'http://',
    ],
)
def test_a_wrong_endpoint_stops_the_server(written: str):
    with pytest.raises(ValidationError) as error:
        make_test_settings(otel_exporter_otlp_endpoint=written)

    # 읽은 값은 오류에 싣지 않는다
    assert 'marked-host' not in str(error.value)


def test_without_an_endpoint_nothing_is_made():
    assert build_provider(make_test_settings()) is None
    assert configure_tracing(make_test_settings()) is None
    shutdown_tracing(None)


@pytest.mark.usefixtures('restore_provider')
def test_shutdown_sends_the_spans_with_the_resource(collector: tuple[Collector, str]):
    received, endpoint = collector
    settings = make_test_settings(otel_exporter_otlp_endpoint=endpoint, app_version='3f2a9c1', app_environment='test')
    provider = configure_tracing(settings)

    with tracer().start_as_current_span('notification.prune'):
        pass
    shutdown_tracing(provider)

    assert received.paths == ['/v1/traces']
    assert received.span_names() == ['notification.prune']
    resource = received.resource()
    assert resource['service.name'] == 'notification-server'
    assert resource['service.version'] == '3f2a9c1'
    assert resource['deployment.environment.name'] == 'test'
    assert resource['service.instance.id'].startswith('server-')
    assert len(resource['service.instance.id']) == len('server-') + 8
    # 정한 넷만 싣는다
    assert set(resource) == {'service.name', 'service.version', 'deployment.environment.name', 'service.instance.id'}


@pytest.mark.usefixtures('restore_provider')
async def test_shutting_down_the_server_sends_what_is_left(
    collector: tuple[Collector, str], auth_server: FakeAuthServer
):
    received, endpoint = collector
    settings = make_test_settings(otel_exporter_otlp_endpoint=endpoint)
    engine = create_engine(settings)
    app = create_app(settings, http_client=auth_server.make_client(), engine=engine)

    async with app.router.lifespan_context(app), make_client(app) as client:
        await client.get('/api/v1/notification/me/notifications')

    assert 'GET /api/v1/notification/me/notifications' in received.span_names()


async def test_a_scope_that_is_not_http_gets_no_span():
    seen: list[dict] = []

    async def inner(scope, receive, send) -> None:
        seen.append(scope)

    await RequestSpanMiddleware(inner)({'type': 'lifespan'}, None, None)

    assert seen == [{'type': 'lifespan'}]
