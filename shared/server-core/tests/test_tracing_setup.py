# shared/server-core/tests/test_tracing_setup.py

"""
span 을 OTLP(HTTP)로 미는 것(server_core/observability/tracing.py)과 그 설정(OTEL_EXPORTER_OTLP_ENDPOINT)을 검증한다.
수집기 대신 이 테스트의 HTTP 서버가 받는다.
"""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.metrics import NoOpMeterProvider
from pydantic import ValidationError

from server_core.observability.metrics import use_meter_provider
from server_core.observability.request_spans import RequestSpanMiddleware
from server_core.observability.spans import tracer, use_provider
from server_core.observability.tracing import build_provider, configure_tracing, shutdown_tracing
from server_core.testing.collector import Collector
from tests.conftest import make_test_settings


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

    with tracer().start_as_current_span('test.probe'):
        pass
    shutdown_tracing(provider)

    assert received.paths == ['/v1/traces']
    assert received.span_names() == ['test.probe']
    # span 을 만든 쪽의 이름과 출처의 서비스 이름이 서버의 이름이다(TestSettings.service_name)
    assert all(scope.scope.name == 'test-server' for scope in received.scopes())
    resource = received.resource()
    assert resource['service.name'] == 'test-server'
    assert resource['service.version'] == '3f2a9c1'
    assert resource['deployment.environment.name'] == 'test'
    assert resource['service.instance.id'].startswith('server-')
    assert len(resource['service.instance.id']) == len('server-') + 8
    # 정한 넷만 싣는다
    assert set(resource) == {'service.name', 'service.version', 'deployment.environment.name', 'service.instance.id'}


async def test_a_scope_that_is_not_http_gets_no_span():
    seen: list[dict] = []

    async def inner(scope, receive, send) -> None:
        seen.append(scope)

    await RequestSpanMiddleware(inner)({'type': 'lifespan'}, None, None)

    assert seen == [{'type': 'lifespan'}]
