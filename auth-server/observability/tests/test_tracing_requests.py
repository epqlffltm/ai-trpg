# auth-server/observability/tests/test_tracing_requests.py

"""
요청마다 서버 span 이 걸리고 로그의 trace_id 가 그 span 의 것인지 검증한다(observability/request_spans.py).
span 은 메모리에 모은다(observability/tests/spans.py). 규격은 docs/observability.md 의 "3. 추적"에 있다.
"""

import logging

from django.test import TestCase, override_settings
from opentelemetry.trace import SpanKind, StatusCode

from observability.spans import ATTRIBUTE_REQUEST_ID
from observability.tests.helpers import rendered
from observability.tests.spans import hex_trace_id, record_spans
from observability.tests.urls_for_tests import SECRET_IN_ERROR

REQUEST_LOGGER = 'observability.middleware'
TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736'
PARENT_ID = '00f067aa0ba902b7'
TRACEPARENT = f'00-{TRACE_ID}-{PARENT_ID}-01'
THING_ID = 'thing-0b9f5e0c'


@override_settings(ROOT_URLCONF='observability.tests.urls_for_tests', DEBUG=False)
class RequestSpanTests(TestCase):
    def setUp(self) -> None:
        self.spans = record_spans(self)
        self.client.raise_request_exception = False

    def only(self):
        ended = self.spans.ended()
        self.assertEqual(len(ended), 1, self.spans.names())
        return ended[0]

    def test_a_request_gets_a_server_span_named_by_its_route(self):
        self.client.get(f'/things/{THING_ID}?secret=query-value')

        span = self.only()
        self.assertEqual(span.name, 'GET /things/<str:thing_id>')
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertEqual(span.attributes['http.route'], '/things/<str:thing_id>')
        self.assertEqual(span.attributes['http.response.status_code'], 200)
        # 주소에 든 값과 주소 뒤의 값은 싣지 않는다
        self.assertNotIn(THING_ID, str(dict(span.attributes)))
        self.assertNotIn('query-value', str(dict(span.attributes)))

    def test_the_log_trace_id_and_the_request_id_follow_the_span(self):
        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            response = self.client.get(f'/things/{THING_ID}')

        span = self.only()
        (line,) = [line for line in rendered(captured.records) if 'status_code' in line]
        self.assertEqual(line['trace_id'], hex_trace_id(span))
        self.assertEqual(span.attributes[ATTRIBUTE_REQUEST_ID], response['X-Request-ID'])

    def test_the_callers_span_becomes_the_parent(self):
        self.client.get(f'/things/{THING_ID}', headers={'traceparent': TRACEPARENT})

        span = self.only()
        self.assertEqual(hex_trace_id(span), TRACE_ID)
        self.assertEqual(f'{span.parent.span_id:016x}', PARENT_ID)
        self.assertTrue(span.parent.is_remote)

    def test_a_caller_that_does_not_record_is_still_recorded(self):
        # span 을 내보내지 않는 서버는 flags 00 을 보낸다. 그것을 따르면 이 서버의 span 이 다 버려진다
        self.client.get(f'/things/{THING_ID}', headers={'traceparent': f'00-{TRACE_ID}-{PARENT_ID}-00'})

        self.assertEqual(hex_trace_id(self.only()), TRACE_ID)

    def test_a_malformed_traceparent_starts_a_new_trace(self):
        for value in (f'00-{TRACE_ID.upper()}-{PARENT_ID}-01', f'00-{"0" * 32}-{PARENT_ID}-01', 'garbage'):
            with self.subTest(value=value):
                self.spans.exporter.clear()
                self.client.get(f'/things/{THING_ID}', headers={'traceparent': value})

                span = self.only()
                self.assertIsNone(span.parent)
                self.assertNotEqual(hex_trace_id(span), TRACE_ID)

    def test_probes_get_no_span(self):
        self.client.get('/health')
        self.client.get('/health/ready')

        self.assertEqual(self.spans.names(), [])

    def test_a_server_error_marks_the_span_without_its_contents(self):
        response = self.client.get(f'/broken/{THING_ID}')

        span = self.only()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes['http.response.status_code'], 500)
        self.assertNotIn(SECRET_IN_ERROR, str(span.status.description))
        self.assertEqual(span.events, ())

    def test_an_unmatched_address_is_marked_but_not_an_error(self):
        self.client.get(f'/no/such/address/{THING_ID}')

        span = self.only()
        self.assertEqual(span.name, 'GET (unmatched)')
        self.assertNotEqual(span.status.status_code, StatusCode.ERROR)

    def test_queries_of_a_request_sit_under_its_span(self):
        self.client.get('/users')

        server = [span for span in self.spans.ended() if span.kind == SpanKind.SERVER]
        queries = [span for span in self.spans.ended() if span.name.startswith('db ')]
        self.assertEqual(len(server), 1)
        self.assertTrue(queries)
        self.assertTrue(all(query.context.trace_id == server[0].context.trace_id for query in queries))
