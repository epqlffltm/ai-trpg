# auth-server/observability/tests/test_metrics_setup.py

"""
메트릭을 OTLP(HTTP)로 미는 것(observability/metrics.py)과 그 설정(OTEL_METRIC_EXPORT_INTERVAL)을 검증한다.
수집기 대신 가짜 수집기(observability/tests/collector.py)가 받는다.
"""

from django.conf import settings
from django.test import SimpleTestCase
from opentelemetry.metrics import NoOpMeterProvider

from config.tests.test_security import run_manage
from observability.formatter import ServiceInfo
from observability.metrics import (
    build_meter_provider,
    configure_metrics,
    instruments,
    record_request,
    use_meter_provider,
)
from observability.tests.collector import Collector
from observability.tracing import build_resource

INFO = ServiceInfo(service='auth-server', environment='test', version='3f2a9c1')


class ExportTests(SimpleTestCase):
    def setUp(self) -> None:
        self.addCleanup(use_meter_provider, NoOpMeterProvider())

    def test_without_an_endpoint_nothing_is_made(self):
        resource = build_resource(INFO, 'server')
        before = instruments()

        self.assertIsNone(build_meter_provider('', 15000, resource))
        self.assertIsNone(configure_metrics('', 15000, resource))
        self.assertIs(instruments(), before)

    def test_shutdown_sends_the_metrics_with_the_resource(self):
        with Collector() as collector:
            provider = configure_metrics(collector.url, 15000, build_resource(INFO, 'server'))
            record_request('GET', '/health', 200, 0.02)
            provider.shutdown()

        self.assertEqual(collector.paths, ['/v1/metrics'])
        requests = collector.metric('http_server_requests')
        labels = {attribute.key: attribute.value for attribute in requests.sum.data_points[0].attributes}
        self.assertEqual(labels['route'].string_value, '/health')
        self.assertEqual(labels['status_code'].int_value, 200)
        # 셈은 쌓이는 값(cumulative)이다. Alloy 가 Prometheus 의 counter 로 바꾼다
        self.assertTrue(requests.sum.is_monotonic)
        self.assertEqual(collector.metric('http_server_request_duration').unit, 's')
        resource = collector.metric_resource()
        self.assertEqual(resource['service.name'], 'auth-server')
        self.assertTrue(resource['service.instance.id'].startswith('server-'))
        self.assertEqual(
            set(resource), {'service.name', 'service.version', 'deployment.environment.name', 'service.instance.id'}
        )


class SettingsTests(SimpleTestCase):
    def test_the_interval_is_fifteen_seconds_by_default(self):
        self.assertEqual(settings.OTEL_METRIC_EXPORT_INTERVAL, 15000)

    def test_an_interval_shorter_than_a_second_stops_the_process(self):
        # 설정은 프로세스에 한 번만 읽힌다. 새 프로세스에서 본다
        result = run_manage('check', OTEL_METRIC_EXPORT_INTERVAL='999')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('OTEL_METRIC_EXPORT_INTERVAL', result.stderr)
