# auth-server/accounts/tests/test_billing_client.py

"""
결제 서버를 부르는 함수를 검증한다.

요청을 보내는 부분을 가짜로 바꾸지 않는다. 이 PC 에 띄운 가짜 결제 서버(billing_stub.py)로 실제로 보내서,
나가는 요청의 모양과 돌아오는 답의 처리를 본다.
"""

import json
import os
import time
import uuid
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from accounts import billing_client
from accounts.billing_client import (
    ALREADY_GRANTED,
    DISABLED,
    GRANTED,
    BillingUnavailableError,
    grant_welcome_credit,
)
from accounts.tests.billing_stub import SECRET, BillingStub, closed_port_url
from config.billing import validate_billing_url, validate_service_secret
from observability.context import request_scope
from observability.identifiers import new_trace

USER_ID = uuid.UUID('11111111-2222-4333-8444-555555555555')


def grant(stub: BillingStub, **settings_overrides) -> str:
    """가짜 결제 서버를 가리키게 설정을 바꾸고 환영 크레딧을 맡긴다."""
    fields = {'BILLING_URL': stub.url, 'BILLING_SERVICE_SECRET': SECRET}
    fields.update(settings_overrides)
    with override_settings(**fields):
        return grant_welcome_credit(user_public_id=USER_ID)


class RequestShapeTests(SimpleTestCase):
    def test_posts_the_user_to_the_welcome_route(self):
        with BillingStub() as stub:
            grant(stub)

        self.assertEqual(len(stub.requests), 1)
        request = stub.requests[0]
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.path, '/api/v1/billing/service/grants/welcome')
        self.assertEqual(request.headers['Content-Type'], 'application/json')
        # 누구에게 줄지만 보낸다. 양은 결제 서버의 설정이 정한다
        self.assertEqual(json.loads(request.body), {'user_id': str(USER_ID)})

    def test_signs_the_exact_bytes_it_sends(self):
        with BillingStub() as stub:
            grant(stub)

        request = stub.requests[0]
        self.assertTrue(request.has_valid_signature())
        # 다른 비밀로는 맞지 않는다. 서명이 정말 그 비밀로 만든 것이다
        self.assertFalse(request.has_valid_signature('another-secret-that-is-32-chars!!'))

    def test_signature_carries_the_current_time(self):
        with BillingStub() as stub:
            grant(stub)

        sent_at = int(stub.requests[0].headers['X-Service-Signature'].partition(',')[0].removeprefix('t='))
        # 결제 서버는 5분 넘게 벌어진 서명을 받지 않는다
        self.assertAlmostEqual(sent_at, time.time(), delta=5)

    def test_never_sends_the_secret_itself(self):
        with BillingStub() as stub:
            grant(stub)

        request = stub.requests[0]
        sent = request.body.decode() + ' '.join(f'{name}: {value}' for name, value in request.headers.items())
        self.assertNotIn(SECRET, sent)

    def test_passes_the_trace_but_not_the_request_id(self):
        trace = new_trace()
        with BillingStub() as stub, request_scope('req-1234567890', trace):
            grant(stub)

        headers = stub.requests[0].headers
        # 같은 흐름(trace_id)으로 이어진다. 결제 서버의 로그와 이 서버의 로그를 그 값으로 잇는다
        self.assertEqual(headers['Traceparent'].split('-')[1], trace.trace_id)
        self.assertNotIn('X-Request-Id', headers)

    def test_ignores_proxies_from_the_environment(self):
        # 개발자의 PC 에 프록시가 잡혀 있어도 우리 서버끼리의 요청은 그리로 나가지 않는다
        dead_proxy = closed_port_url()
        # NO_PROXY 도 비운다. 이 PC 의 주소는 프록시를 거치지 않는다고 적혀 있으면 프록시를 쓰는 코드도 통과한다
        proxies = {'HTTP_PROXY': dead_proxy, 'http_proxy': dead_proxy, 'NO_PROXY': '', 'no_proxy': ''}
        with BillingStub() as stub, patch.dict(os.environ, proxies):
            outcome = grant(stub)

        self.assertEqual(outcome, GRANTED)
        self.assertEqual(len(stub.requests), 1)


class OutcomeTests(SimpleTestCase):
    def test_reads_the_three_finished_outcomes(self):
        answers = {
            GRANTED: (201, b'{"status":"granted","granted":"1000","expires_at":"2026-03-09T09:00:00Z"}'),
            ALREADY_GRANTED: (200, b'{"status":"already_granted","granted":"0","expires_at":null}'),
            DISABLED: (200, b'{"status":"disabled","granted":"0","expires_at":null}'),
        }
        for outcome, (status_code, body) in answers.items():
            with self.subTest(outcome), BillingStub(status_code=status_code, body=body) as stub:
                self.assertEqual(grant(stub), outcome)

    def test_any_other_status_code_means_try_again_later(self):
        # 401 은 비밀이 어긋났거나 시계가 벌어진 것이다. 설정을 고치면 되므로 버리지 않고 다시 시도한다
        for status_code in (400, 401, 404, 409, 500, 503):
            with self.subTest(status_code), BillingStub(status_code=status_code, body=b'{"detail":"..."}') as stub:
                with self.assertRaisesMessage(BillingUnavailableError, str(status_code)):
                    grant(stub)

    def test_success_code_with_an_unreadable_answer_is_not_trusted(self):
        bodies = {
            'JSON 이 아니다': b'<html>ok</html>',
            '비었다': b'',
            '목록이다': b'["granted"]',
            'status 가 없다': b'{"granted":"1000"}',
            '모르는 결과다': b'{"status":"maybe"}',
        }
        for name, body in bodies.items():
            with self.subTest(name), BillingStub(status_code=200, body=body) as stub:
                with self.assertRaises(BillingUnavailableError):
                    grant(stub)


class UnreachableTests(SimpleTestCase):
    def test_connection_refused_is_reported_without_the_address(self):
        url = closed_port_url()

        with override_settings(BILLING_URL=url, BILLING_SERVICE_SECRET=SECRET):
            with self.assertRaises(BillingUnavailableError) as raised:
                grant_welcome_credit(user_public_id=USER_ID)

        self.assertNotIn(url.rpartition(':')[2], str(raised.exception))
        self.assertNotIn(SECRET, str(raised.exception))

    def test_does_not_wait_forever_for_an_answer(self):
        with BillingStub(delay_seconds=30) as stub, patch.object(billing_client, 'TIMEOUT_SECONDS', 0.2):
            started = time.monotonic()
            with self.assertRaises(BillingUnavailableError):
                grant(stub)

        self.assertLess(time.monotonic() - started, 5)

    def test_does_not_follow_redirects(self):
        # 서명한 요청이 우리가 고르지 않은 주소로 가면 안 된다
        with BillingStub() as elsewhere:
            redirect = {'Location': elsewhere.url + '/api/v1/billing/service/grants/welcome'}
            for status_code in (301, 302, 307, 308):
                with self.subTest(status_code), BillingStub(status_code=status_code, headers=redirect) as stub:
                    with self.assertRaises(BillingUnavailableError):
                        grant(stub)

        self.assertEqual(elsewhere.requests, [])

    def test_without_a_secret_nothing_is_sent(self):
        with BillingStub() as stub:
            with self.assertRaisesMessage(BillingUnavailableError, 'BILLING_SERVICE_SECRET'):
                grant(stub, BILLING_SERVICE_SECRET='')

        self.assertEqual(stub.requests, [])


class SettingsTests(SimpleTestCase):
    def test_billing_url_must_be_http(self):
        for url in ('', '127.0.0.1:8003', 'file:///etc/passwd', 'ftp://billing.example.com', 'http://'):
            with self.subTest(url), self.assertRaises(ImproperlyConfigured):
                validate_billing_url(url)

    def test_billing_url_loses_its_trailing_slash(self):
        self.assertEqual(validate_billing_url('http://127.0.0.1:8003/'), 'http://127.0.0.1:8003')
        self.assertEqual(validate_billing_url('https://billing.example.com'), 'https://billing.example.com')

    def test_secret_may_be_empty_but_not_short(self):
        self.assertEqual(validate_service_secret(''), '')
        self.assertEqual(validate_service_secret('s' * 32), 's' * 32)
        with self.assertRaises(ImproperlyConfigured) as raised:
            validate_service_secret('short-secret-value')
        # 오류에 값을 싣지 않는다
        self.assertNotIn('short-secret-value', str(raised.exception))
