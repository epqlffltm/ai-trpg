# auth-server/observability/tests/collector.py

"""
OTLP(HTTP)로 오는 span 과 메트릭을 받는 가짜 수집기. 따로 도는 스레드에서 받는다.
보내는 길(observability/tracing.py, metrics.py)을 보는 테스트가 with 로 띄운다.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

TRACES_PATH = '/v1/traces'
METRICS_PATH = '/v1/metrics'


def attributes_of(resource) -> dict[str, str]:
    """출처의 속성. 모두 글자다."""
    return {attribute.key: attribute.value.string_value for attribute in resource.attributes}


class Collector:
    """OTLP 로 온 span 과 메트릭을 모은다. with 로 띄우고 끈다. 주소(경로 없이)는 url 이다."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        self.requests: list[ExportTraceServiceRequest] = []
        self.metric_requests: list[ExportMetricsServiceRequest] = []
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

    def receive(self, path: str, body: bytes) -> None:
        """받은 본문을 주소에 맞는 모양으로 읽어 둔다."""
        with self.lock:
            self.paths.append(path)
            if path == TRACES_PATH:
                request = ExportTraceServiceRequest()
                request.ParseFromString(body)
                self.requests.append(request)
            elif path == METRICS_PATH:
                request = ExportMetricsServiceRequest()
                request.ParseFromString(body)
                self.metric_requests.append(request)

    def handler(self) -> type[BaseHTTPRequestHandler]:
        collector = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                collector.receive(self.path, self.rfile.read(int(self.headers['Content-Length'])))
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
            return attributes_of(self.requests[0].resource_spans[0].resource)

    def metric(self, name: str):
        """그 이름의 메트릭(처음 받은 것)."""
        with self.lock:
            return next(
                metric
                for request in self.metric_requests
                for resource in request.resource_metrics
                for scope in resource.scope_metrics
                for metric in scope.metrics
                if metric.name == name
            )

    def metric_resource(self) -> dict[str, str]:
        """처음 받은 메트릭의 출처."""
        with self.lock:
            return attributes_of(self.metric_requests[0].resource_metrics[0].resource)
