# auth-server/observability/tests/test_tracing_setup.py

"""
span 을 OTLP(HTTP)로 미는 것(observability/tracing.py)과 그 설정(OTEL_EXPORTER_OTLP_ENDPOINT),
프로세스가 뜰 때 거는 일(observability/apps.py)을 검증한다.
수집기 대신 가짜 수집기(observability/tests/collector.py)가 받는다.
"""

from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from opentelemetry import trace
from opentelemetry.metrics import NoOpMeterProvider

from observability import apps
from observability.formatter import ServiceInfo
from observability.metrics import use_meter_provider
from observability.spans import record_handled, tracer, use_provider
from observability.tests.collector import Collector
from observability.tracing import build_provider, build_resource, configure_tracing, otlp_endpoint

INFO = ServiceInfo(service='auth-server', environment='test', version='3f2a9c1')
MAIL_WORKER = build_resource(INFO, 'send_outgoing_mail')


class EndpointTests(SimpleTestCase):
    def test_the_endpoint_is_read_without_a_path(self):
        cases = {'': '', '  ': '', 'http://alloy:4318': 'http://alloy:4318', 'https://a.b:4318/': 'https://a.b:4318'}
        for written, read in cases.items():
            with self.subTest(written=written):
                self.assertEqual(otlp_endpoint(written), read)

    def test_a_wrong_endpoint_is_refused(self):
        for written in (
            'http://alloy:4318/v1/traces',
            'alloy:4318',
            'ftp://alloy:4318',
            'http://alloy:4318?x=1',
            'http://',
        ):
            with self.subTest(written=written), self.assertRaises(ValueError):
                otlp_endpoint(written)


class ExportTests(SimpleTestCase):
    def setUp(self) -> None:
        self.addCleanup(use_provider, trace.NoOpTracerProvider())

    def test_without_an_endpoint_nothing_is_made(self):
        self.assertIsNone(build_provider('', MAIL_WORKER))
        self.assertIsNone(configure_tracing('', MAIL_WORKER))

    def test_shutdown_sends_the_spans_with_the_resource(self):
        with Collector() as collector:
            provider = configure_tracing(collector.url, MAIL_WORKER)
            with tracer().start_as_current_span('GET /api/v1/auth/jwks'):
                pass
            provider.shutdown()

        self.assertEqual(collector.paths, ['/v1/traces'])
        self.assertEqual(collector.span_names(), ['GET /api/v1/auth/jwks'])
        resource = collector.resource()
        self.assertEqual(resource['service.name'], 'auth-server')
        self.assertEqual(resource['service.version'], '3f2a9c1')
        self.assertEqual(resource['deployment.environment.name'], 'test')
        self.assertTrue(resource['service.instance.id'].startswith('send_outgoing_mail-'))
        self.assertEqual(
            set(resource), {'service.name', 'service.version', 'deployment.environment.name', 'service.instance.id'}
        )

    def test_idle_rounds_are_not_sent_by_the_server_either(self):
        with Collector() as collector:
            provider = configure_tracing(collector.url, MAIL_WORKER)
            with tracer().start_as_current_span('mail.deliver_outgoing', attributes={'job_id': 'job-1'}):
                record_handled(0)
            provider.shutdown()

        self.assertEqual(collector.span_names(), [])


class StartTests(SimpleTestCase):
    def setUp(self) -> None:
        self.addCleanup(use_provider, trace.NoOpTracerProvider())
        self.addCleanup(use_meter_provider, NoOpMeterProvider())

    def test_the_process_is_named_by_its_command(self):
        self.assertEqual(
            apps.process_name(['/app/manage.py', 'send_outgoing_mail', '--interval', '1']), 'send_outgoing_mail'
        )
        self.assertEqual(apps.process_name(['manage.py']), 'server')
        self.assertEqual(apps.process_name(['/usr/local/bin/gunicorn', 'config.wsgi']), 'server')

    def test_tests_never_send(self):
        with patch.object(apps, 'configure_tracing') as tracing, patch.object(apps, 'configure_metrics') as metrics:
            apps.start_telemetry(['manage.py', 'test'])

        tracing.assert_not_called()
        metrics.assert_not_called()

    @override_settings(OTEL_EXPORTER_OTLP_ENDPOINT='http://alloy:4318', OTEL_METRIC_EXPORT_INTERVAL=5000)
    def test_other_processes_send_spans_and_metrics_from_one_resource(self):
        with patch.object(apps, 'configure_tracing') as tracing, patch.object(apps, 'configure_metrics') as metrics:
            apps.start_telemetry(['/app/manage.py', 'send_welcome_credits'])

        endpoint, resource = tracing.call_args.args
        self.assertEqual(endpoint, 'http://alloy:4318')
        self.assertEqual(resource.attributes['service.name'], 'auth-server')
        self.assertEqual(resource.attributes['deployment.environment.name'], settings.APP_ENVIRONMENT)
        self.assertTrue(resource.attributes['service.instance.id'].startswith('send_welcome_credits-'))
        # 메트릭도 같은 출처다(같은 service.instance.id)
        self.assertEqual(metrics.call_args.args, ('http://alloy:4318', 5000, resource))
