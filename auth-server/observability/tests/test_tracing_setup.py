# auth-server/observability/tests/test_tracing_setup.py

"""
span 을 OTLP(HTTP)로 미는 것(observability/tracing.py)과 그 설정(OTEL_EXPORTER_OTLP_ENDPOINT),
프로세스가 뜰 때 거는 일(observability/apps.py)을 검증한다. 수집기 대신 이 테스트의 HTTP 서버가 받는다.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from observability import apps
from observability.formatter import ServiceInfo
from observability.spans import record_handled, tracer, use_provider
from observability.tracing import build_provider, configure_tracing, otlp_endpoint

INFO = ServiceInfo(service='auth-server', environment='test', version='3f2a9c1')


class Collector:
    """OTLP 로 온 span 을 모으는 가짜 수집기. 따로 도는 스레드에서 받는다."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        self.requests: list[ExportTraceServiceRequest] = []
        self.lock = threading.Lock()
        self.server = HTTPServer(('127.0.0.1', 0), self.handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> 'Collector':
        self.thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.server.shutdown()
        self.server.server_close()

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.server.server_port}'

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
        with self.lock:
            return [
                span.name
                for request in self.requests
                for resource in request.resource_spans
                for scope in resource.scope_spans
                for span in scope.spans
            ]

    def resource(self) -> dict[str, str]:
        with self.lock:
            attributes = self.requests[0].resource_spans[0].resource.attributes
        return {attribute.key: attribute.value.string_value for attribute in attributes}


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
        self.assertIsNone(build_provider('', INFO, 'server'))
        self.assertIsNone(configure_tracing('', INFO, 'server'))

    def test_shutdown_sends_the_spans_with_the_resource(self):
        with Collector() as collector:
            provider = configure_tracing(collector.url, INFO, 'send_outgoing_mail')
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
            provider = configure_tracing(collector.url, INFO, 'send_outgoing_mail')
            with tracer().start_as_current_span('mail.deliver_outgoing', attributes={'job_id': 'job-1'}):
                record_handled(0)
            provider.shutdown()

        self.assertEqual(collector.span_names(), [])


class StartTests(SimpleTestCase):
    def setUp(self) -> None:
        self.addCleanup(use_provider, trace.NoOpTracerProvider())

    def test_the_process_is_named_by_its_command(self):
        self.assertEqual(
            apps.process_name(['/app/manage.py', 'send_outgoing_mail', '--interval', '1']), 'send_outgoing_mail'
        )
        self.assertEqual(apps.process_name(['manage.py']), 'server')
        self.assertEqual(apps.process_name(['/usr/local/bin/gunicorn', 'config.wsgi']), 'server')

    def test_tests_never_send(self):
        with patch.object(apps, 'configure_tracing') as configure:
            apps.start_tracing(['manage.py', 'test'])

        configure.assert_not_called()

    @override_settings(OTEL_EXPORTER_OTLP_ENDPOINT='http://alloy:4318')
    def test_other_processes_send_to_the_endpoint(self):
        with patch.object(apps, 'configure_tracing') as configure:
            apps.start_tracing(['/app/manage.py', 'send_welcome_credits'])

        endpoint, info, process = configure.call_args.args
        self.assertEqual(endpoint, 'http://alloy:4318')
        self.assertEqual(info.service, 'auth-server')
        self.assertEqual(info.environment, settings.APP_ENVIRONMENT)
        self.assertEqual(process, 'send_welcome_credits')
