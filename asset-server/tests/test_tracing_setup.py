# asset-server/tests/test_tracing_setup.py

"""
span 을 OTLP(HTTP)로 미는 것(app/observability/tracing.py)과 그 설정(OTEL_EXPORTER_OTLP_ENDPOINT)을 검증한다.
수집기 대신 이 테스트의 HTTP 서버가 받는다.
"""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.metrics import NoOpMeterProvider
from pydantic import ValidationError

from app.core.database import create_engine
from app.main import create_app
from app.observability.metrics import use_meter_provider
from app.observability.request_spans import RequestSpanMiddleware
from app.observability.spans import tracer, use_provider
from app.observability.tracing import build_provider, configure_tracing, shutdown_tracing
from tests.collector import Collector
from tests.conftest import make_client, make_test_settings
from tests.tokens import FakeAuthServer


@pytest.fixture
def restore_provider() -> Iterator[None]:
    """끼운 TracerProvider 와 MeterProvider 를 테스트가 끝나면 아무것도 하지 않는 것으로 되돌린다."""
    yield
    use_provider(trace.NoOpTracerProvider())
    use_meter_provider(NoOpMeterProvider())


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

    with tracer().start_as_current_span('asset.probe'):
        pass
    shutdown_tracing(provider)

    assert received.paths == ['/v1/traces']
    assert received.span_names() == ['asset.probe']
    resource = received.resource()
    assert resource['service.name'] == 'asset-server'
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
        await client.get('/api/v1/asset/me')

    assert 'GET /api/v1/asset/me' in received.span_names()
    assert 'http_server_requests' in received.metric_names()
    # FastAPI 가 스스로 내보내는 것(span, 메트릭, 로그)은 없다. 우리가 만든 것만 간다
    assert set(received.paths) == {'/v1/traces', '/v1/metrics'}
    assert all(scope.scope.name == 'asset-server' for scope in received.scopes())
    assert all(scope.scope.name == 'asset-server' for scope in received.metric_scopes())
    # span 과 메트릭이 한 출처다(같은 service.instance.id)
    assert received.resource() == received.metric_resource()


async def test_a_scope_that_is_not_http_gets_no_span():
    seen: list[dict] = []

    async def inner(scope, receive, send) -> None:
        seen.append(scope)

    await RequestSpanMiddleware(inner)({'type': 'lifespan'}, None, None)

    assert seen == [{'type': 'lifespan'}]
