# auth-server/observability/tests/test_requests.py

"""
요청마다 식별자가 걸리고 끝나면 한 줄이 남는지 검증한다(observability/middleware.py).
요청을 실제 미들웨어들을 거쳐 보내고, 응답의 머리말과 남은 로그를 본다. 규격은 docs/observability.md 에 있다.
"""

import logging
import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework import status

from observability.tests.helpers import rendered

REQUEST_LOGGER = 'observability.middleware'
TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736'
TRACEPARENT = f'00-{TRACE_ID}-00f067aa0ba902b7-01'
# 서명까지 갖춘 토큰의 모양. 실제 키로 만든 것이 아니다
FAKE_TOKEN = 'eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVlLWhlcmU'
JWKS_URL = reverse('accounts:jwks')
LOGIN_URL = reverse('accounts:login')
MALFORMED_REQUEST_IDS = [
    'short',
    'a' * 65,
    'a' * 3000,
    'has space in it',
    '{"level":"error"}',
    'semi;colon-12345',
    # 같은 머리말이 두 번 오면 WSGI 가 쉼표로 이어 준다. 어느 것을 믿을지 정할 수 없다
    'client-chosen-id-0001,client-chosen-id-0002',
]


class RequestIdTests(TestCase):
    def finished_line(self, captured) -> dict:
        """요청이 끝났다는 줄. 하나여야 한다."""
        (line,) = [line for line in rendered(captured.records) if 'status_code' in line]
        return line

    def test_a_request_without_an_id_gets_a_new_one(self):
        response = self.client.get(JWKS_URL)

        request_id = response['X-Request-ID']
        self.assertEqual(str(uuid.UUID(request_id)), request_id)

    def test_every_request_gets_a_different_id(self):
        first = self.client.get(JWKS_URL)
        second = self.client.get(JWKS_URL)

        self.assertNotEqual(first['X-Request-ID'], second['X-Request-ID'])

    def test_a_well_formed_id_is_kept(self):
        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            response = self.client.get(JWKS_URL, headers={'X-Request-ID': 'client-chosen-id-0001'})

        self.assertEqual(response['X-Request-ID'], 'client-chosen-id-0001')
        self.assertEqual(self.finished_line(captured)['request_id'], 'client-chosen-id-0001')

    def test_a_malformed_id_is_replaced(self):
        for value in MALFORMED_REQUEST_IDS:
            with self.subTest(value=value[:30]), self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
                response = self.client.get(JWKS_URL, headers={'X-Request-ID': value})

                request_id = response['X-Request-ID']
                self.assertEqual(str(uuid.UUID(request_id)), request_id)
                # 받은 값은 응답에도 로그에도 남지 않는다
                self.assertNotIn(value, str(rendered(captured.records)))

    def test_control_characters_in_the_id_never_reach_the_log(self):
        injected = 'request-12345\r\n{"level":"error","message":"forged"}'

        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            response = self.client.get(
                JWKS_URL, headers={'X-Request-ID': injected, 'traceparent': f'{TRACEPARENT}\nforged'}
            )

        line = self.finished_line(captured)
        self.assertEqual(str(uuid.UUID(line['request_id'])), line['request_id'])
        self.assertEqual(response['X-Request-ID'], line['request_id'])
        self.assertNotEqual(line['trace_id'], TRACE_ID)
        self.assertNotIn('forged', str(line))

    def test_the_trace_is_carried_on_from_the_caller(self):
        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            self.client.get(JWKS_URL, headers={'traceparent': TRACEPARENT})

        self.assertEqual(self.finished_line(captured)['trace_id'], TRACE_ID)


class FinishedLineTests(TestCase):
    def finished_line(self, captured) -> dict:
        (line,) = [line for line in rendered(captured.records) if 'status_code' in line]
        return line

    def test_the_finished_line_has_the_common_fields(self):
        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            response = self.client.get(JWKS_URL)

        line = self.finished_line(captured)
        for field in ('timestamp', 'level', 'service', 'environment', 'version', 'request_id', 'trace_id'):
            self.assertTrue(line[field], field)
        self.assertEqual(line['operation'], 'http.request')
        self.assertEqual(line['method'], 'GET')
        self.assertEqual(line['route'], '/api/v1/auth/jwks')
        self.assertEqual(line['status_code'], status.HTTP_200_OK)
        self.assertEqual(line['result'], 'success')
        self.assertEqual(line['level'], 'info')
        self.assertIsInstance(line['duration_ms'], int)
        self.assertEqual(line['request_id'], response['X-Request-ID'])
        self.assertRegex(line['trace_id'], r'^[0-9a-f]{32}$')

    def test_a_client_error_is_info_and_marked_as_the_clients(self):
        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            response = self.client.post(LOGIN_URL, {}, content_type='application/json')

        line = self.finished_line(captured)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(line['status_code'], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(line['result'], 'client_error')
        # 요청이 틀린 것이다. 서버는 제 일을 했다. 경고로 올리지 않는다
        self.assertEqual(line['level'], 'info')

    def test_an_unknown_address_logs_the_real_path_separately(self):
        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            response = self.client.get('/no/such/address?secret=query-value')

        line = self.finished_line(captured)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # 맞는 틀이 없다. 틀 자리에 실제 주소를 넣지 않는다
        self.assertEqual(line['route'], '(unmatched)')
        self.assertEqual(line['path'], '/no/such/address')
        # 주소 뒤에 붙인 값은 남지 않는다
        self.assertNotIn('query-value', str(line))

    def test_the_request_body_and_credentials_never_reach_the_log(self):
        body = {'username': 'someone', 'password': 'my-secret-password-123'}
        headers = {'Authorization': f'Bearer {FAKE_TOKEN}', 'Cookie': 'refresh_token=cookie-secret-value'}

        with self.assertLogs(level=logging.DEBUG) as captured:
            self.client.post(LOGIN_URL, body, content_type='application/json', headers=headers)

        everything = str(rendered(captured.records))
        self.assertNotIn('my-secret-password-123', everything)
        self.assertNotIn(FAKE_TOKEN, everything)
        self.assertNotIn('cookie-secret-value', everything)

    def test_django_does_not_log_the_real_path_of_a_client_error_again(self):
        with self.assertLogs(level=logging.DEBUG) as captured:
            self.client.get('/no/such/address/with-user-input-9f8e7d')

        # Django 의 "Not Found: /주소" 줄은 버린다. 요청이 끝난 줄 하나만 남는다
        lines = [line for line in rendered(captured.records) if 'with-user-input-9f8e7d' in str(line)]
        self.assertEqual([line['logger'] for line in lines], [REQUEST_LOGGER])


@override_settings(ROOT_URLCONF='observability.tests.urls_for_tests', DEBUG=False)
class UnhandledExceptionTests(TestCase):
    def setUp(self):
        # 예외를 테스트로 올리지 않고 서버가 내보내는 500 응답을 그대로 받는다
        self.client = Client(raise_request_exception=False)

    def test_the_route_is_logged_as_a_template_not_the_real_path(self):
        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            self.client.get('/things/thing-with-user-input-1234?secret=query-value')

        (line,) = rendered(captured.records)
        self.assertEqual(line['route'], '/things/<str:thing_id>')
        self.assertNotIn('thing-with-user-input-1234', str(line))
        self.assertNotIn('query-value', str(line))

    def test_an_unhandled_exception_is_logged_with_the_request_id(self):
        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            response = self.client.get('/broken/thing-1234', headers={'traceparent': TRACEPARENT})

        (error_line,) = [line for line in rendered(captured.records) if 'stack_trace' in line]
        self.assertEqual(error_line['level'], 'error')
        self.assertEqual(error_line['request_id'], response['X-Request-ID'])
        self.assertEqual(error_line['trace_id'], TRACE_ID)
        self.assertEqual(error_line['operation'], 'http.request')
        self.assertEqual(error_line['error_code'], 'http.unhandled_exception')
        self.assertEqual(error_line['error_type'], 'RuntimeError')
        self.assertEqual(error_line['route'], '/broken/<str:thing_id>')
        self.assertIn('RuntimeError', error_line['stack_trace'])
        # 예외의 글에 든 비밀번호는 로그에서도 가려진다
        self.assertNotIn('super-secret', str(error_line))

    def test_a_server_error_is_logged_as_an_error(self):
        with self.assertLogs(REQUEST_LOGGER, logging.INFO) as captured:
            self.client.get('/broken/thing-1234')

        (line,) = [line for line in rendered(captured.records) if 'status_code' in line]
        self.assertEqual(line['status_code'], status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(line['result'], 'server_error')
        self.assertEqual(line['level'], 'error')

    def test_the_exception_is_logged_once(self):
        with self.assertLogs(level=logging.DEBUG) as captured:
            self.client.get('/broken/thing-1234')

        # Django 가 같은 예외를 다시 적는 줄은 버린다
        with_stack = [line for line in rendered(captured.records) if 'stack_trace' in line]
        self.assertEqual(len(with_stack), 1)

    def test_the_500_response_does_not_reveal_the_exception(self):
        response = self.client.get('/broken/thing-1234')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        text = response.content.decode()
        self.assertNotIn('super-secret', text)
        self.assertNotIn('RuntimeError', text)
        self.assertNotIn('Traceback', text)
        # 문제를 알릴 때 쓸 식별자는 돌려준다
        self.assertTrue(response['X-Request-ID'])
