# asset-server/tests/test_metrics_setup.py

"""
메트릭을 OTLP(HTTP)로 미는 것(app/observability/metrics.py)과 그 설정(OTEL_METRIC_EXPORT_INTERVAL)을 검증한다.
수집기 대신 이 테스트의 HTTP 서버가 받는다(tests/collector.py).
"""

from collections.abc import Iterator

import pytest
from opentelemetry.metrics import NoOpMeterProvider
from pydantic import ValidationError

from app.observability.metrics import (
    build_meter_provider,
    configure_metrics,
    instruments,
    record_request,
    shutdown_metrics,
    use_meter_provider,
)
from app.observability.tracing import build_resource
from tests.collector import Collector
from tests.conftest import make_test_settings


@pytest.fixture
def restore_meter_provider() -> Iterator[None]:
    """끼운 MeterProvider 를 테스트가 끝나면 아무것도 하지 않는 것으로 되돌린다."""
    yield
    use_meter_provider(NoOpMeterProvider())


def test_the_interval_is_fifteen_seconds_by_default():
    assert make_test_settings().otel_metric_export_interval == 15000


def test_an_interval_shorter_than_a_second_stops_the_server():
    with pytest.raises(ValidationError):
        make_test_settings(otel_metric_export_interval=999)


def test_without_an_endpoint_nothing_is_made():
    settings = make_test_settings()
    before = instruments()

    assert build_meter_provider(settings, build_resource(settings)) is None
    assert configure_metrics(settings, build_resource(settings)) is None
    assert instruments() is before
    shutdown_metrics(None)


@pytest.mark.usefixtures('restore_meter_provider')
def test_shutdown_sends_the_metrics_with_the_resource(collector: tuple[Collector, str]):
    received, endpoint = collector
    settings = make_test_settings(otel_exporter_otlp_endpoint=endpoint, app_version='3f2a9c1', app_environment='test')
    provider = configure_metrics(settings, build_resource(settings))

    record_request('GET', '/health', 200, 0.02)
    shutdown_metrics(provider)

    assert received.paths == ['/v1/metrics']
    requests = received.metric('http_server_requests')
    point = requests.sum.data_points[0]
    labels = {attribute.key: attribute.value for attribute in point.attributes}
    assert labels['method'].string_value == 'GET'
    assert labels['route'].string_value == '/health'
    assert labels['status_code'].int_value == 200
    # 셈은 쌓이는 값(cumulative)이다. Alloy 가 Prometheus 의 counter 로 바꾼다
    assert requests.sum.is_monotonic
    assert received.metric('http_server_request_duration').unit == 's'
    resource = received.metric_resource()
    assert resource['service.name'] == 'asset-server'
    assert resource['service.version'] == '3f2a9c1'
    assert resource['service.instance.id'].startswith('server-')
    assert set(resource) == {'service.name', 'service.version', 'deployment.environment.name', 'service.instance.id'}
