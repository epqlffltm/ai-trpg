# auth-server/observability/tests/test_tracing_http.py

"""
결제 서버를 부르는 요청에 client span 이 걸리는지 검증한다(observability/http_spans.py, accounts/billing_client.py).
가짜 결제 서버(accounts/tests/billing_stub.py)로 실제로 보낸다.
"""

import uuid

from django.test import SimpleTestCase, override_settings
from opentelemetry.trace import SpanKind, StatusCode

from accounts.billing_client import BillingUnavailableError, grant_welcome_credit
from accounts.tests.billing_stub import SECRET, BillingStub, closed_port_url
from observability.http_spans import client_span, mark_unreachable, record_status
from observability.tests.spans import record_spans, traceparent_of

USER_ID = uuid.UUID('11111111-2222-4333-8444-555555555555')


def grant(url: str) -> str:
    """그 주소의 결제 서버에 환영 크레딧을 맡긴다."""
    with override_settings(BILLING_URL=url, BILLING_SECRET=SECRET):
        return grant_welcome_credit(user_public_id=USER_ID)


class ClientSpanTests(SimpleTestCase):
    def setUp(self) -> None:
        self.spans = record_spans(self)

    def test_calling_billing_under_a_span_gets_a_client_span(self):
        with BillingStub() as stub, self.spans.parent() as parent:
            grant(stub.url)

        span = self.spans.find('HTTP POST')
        self.assertEqual(span.kind, SpanKind.CLIENT)
        self.assertEqual(span.parent.span_id, parent.get_span_context().span_id)
        self.assertEqual(span.attributes['server.address'], '127.0.0.1')
        self.assertEqual(span.attributes['http.response.status_code'], 201)
        # 주소의 경로는 싣지 않는다
        self.assertNotIn('grants', str(dict(span.attributes)))
        # 결제 서버의 span 이 이 span 아래에 붙는다
        self.assertEqual(stub.requests[0].headers['Traceparent'], traceparent_of(span))

    def test_a_server_error_marks_the_span(self):
        with BillingStub(status_code=503) as stub, self.spans.parent(), self.assertRaises(BillingUnavailableError):
            grant(stub.url)

        self.assertEqual(self.spans.find('HTTP POST').status.status_code, StatusCode.ERROR)

    def test_a_client_error_does_not_mark_the_span(self):
        with BillingStub(status_code=409) as stub, self.spans.parent(), self.assertRaises(BillingUnavailableError):
            grant(stub.url)

        span = self.spans.find('HTTP POST')
        self.assertEqual(span.attributes['http.response.status_code'], 409)
        self.assertNotEqual(span.status.status_code, StatusCode.ERROR)

    def test_an_unreachable_server_marks_the_span_without_the_address(self):
        url = closed_port_url()
        with self.spans.parent(), self.assertRaises(BillingUnavailableError):
            grant(url)

        span = self.spans.find('HTTP POST')
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertNotIn('127.0.0.1:', str(span.status.description))

    def test_a_call_without_a_parent_gets_no_span(self):
        with BillingStub() as stub:
            grant(stub.url)

        self.assertEqual(self.spans.names(), [])
        self.assertNotIn('Traceparent', stub.requests[0].headers)

    def test_the_helpers_do_nothing_without_a_span(self):
        with client_span('POST', 'http://billing.test/x') as span:
            record_status(span, 500)
            mark_unreachable(span)

        self.assertIsNone(span)
        self.assertEqual(self.spans.names(), [])
