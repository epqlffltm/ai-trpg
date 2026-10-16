# auth-server/config/tests/test_health.py

"""
상태 확인 주소(config/health.py)를 실제 요청으로 확인한다.

규격(저장소 루트의 docs/observability.md)이 정한 것: 본문은 정확히 {"status": ...} 하나, health 는 DB 를 보지 않는다,
readiness 는 DB 에 닿지 않으면 503 이고 이유를 응답에 싣지 않는다.
"""

import logging
from unittest import mock

from django.conf import settings
from django.db import OperationalError
from django.test import TestCase

from observability.tests.helpers import rendered

REQUEST_LOGGER = 'observability.middleware'
# DB 에 닿지 않을 때의 오류. 실제 오류의 글처럼 접속 주소와 계정이 들어 있다
UNREACHABLE = OperationalError(
    'connection to server at "10.0.0.9", port 5432 failed: password authentication failed for user "auth"'
)


class HealthTests(TestCase):
    def test_health_is_ok(self):
        response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_the_body_is_written_like_the_other_servers(self):
        response = self.client.get('/health')

        self.assertEqual(response.content, b'{"status":"ok"}')

    def test_health_does_not_look_at_the_database(self):
        with mock.patch('config.health.ping_database', side_effect=UNREACHABLE) as ping:
            response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        ping.assert_not_called()

    def test_health_carries_a_request_id(self):
        response = self.client.get('/health')

        self.assertTrue(response.headers.get('X-Request-ID'))

    def test_health_answers_head_without_a_body(self):
        response = self.client.head('/health')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'')

    def test_health_takes_only_get_and_head(self):
        response = self.client.post('/health')

        self.assertEqual(response.status_code, 405)


class ReadinessTests(TestCase):
    def test_ready_when_the_database_answers(self):
        response = self.client.get('/health/ready')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_unavailable_when_the_database_does_not_answer(self):
        with mock.patch('config.health.ping_database', side_effect=UNREACHABLE):
            response = self.client.get('/health/ready')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b'{"status":"unavailable"}')

    def test_the_reason_goes_to_the_log_without_the_address(self):
        with (
            mock.patch('config.health.ping_database', side_effect=UNREACHABLE),
            self.assertLogs('config.health', level='WARNING') as logs,
        ):
            self.client.get('/health/ready')

        line = logs.output[0]
        self.assertIn('OperationalError', line)
        self.assertNotIn('10.0.0.9', line)
        self.assertNotIn('password', line)

    def test_ready_answers_head_like_get(self):
        ready = self.client.head('/health/ready')
        with mock.patch('config.health.ping_database', side_effect=UNREACHABLE):
            unavailable = self.client.head('/health/ready')

        self.assertEqual((ready.status_code, ready.content), (200, b''))
        self.assertEqual((unavailable.status_code, unavailable.content), (503, b''))

    def test_ready_takes_only_get_and_head(self):
        response = self.client.post('/health/ready')

        self.assertEqual(response.status_code, 405)


class ProbeLogTests(TestCase):
    """상태 확인 요청이 끝난 줄의 수준. 관리 도구가 10초마다 부르므로 성공은 운영의 수준(info)에서 남지 않는다."""

    def finished_line(self, captured) -> dict:
        (line,) = [line for line in rendered(captured.records) if 'status_code' in line]
        return line

    def test_a_successful_probe_is_debug(self):
        for url in ('/health', '/health/ready'):
            with self.subTest(url=url), self.assertLogs(REQUEST_LOGGER, logging.DEBUG) as captured:
                self.client.get(url)

                line = self.finished_line(captured)
                self.assertEqual((line['level'], line['route']), ('debug', url))

    def test_a_successful_probe_is_not_written_at_info(self):
        with self.assertNoLogs(REQUEST_LOGGER, logging.INFO):
            self.client.get('/health')

    def test_an_unavailable_probe_is_a_warning_not_an_error(self):
        with (
            mock.patch('config.health.ping_database', side_effect=UNREACHABLE),
            self.assertLogs(REQUEST_LOGGER, logging.DEBUG) as captured,
        ):
            self.client.get('/health/ready')

        line = self.finished_line(captured)
        # 503 은 이 주소의 답이다. 서버의 잘못(error)이 아니다. 결과 칸은 다른 5xx 처럼 server_error 다
        self.assertEqual((line['level'], line['status_code'], line['result']), ('warning', 503, 'server_error'))

    def test_django_does_not_add_an_error_line_for_an_unavailable_probe(self):
        with (
            mock.patch('config.health.ping_database', side_effect=UNREACHABLE),
            self.assertNoLogs('django.request', logging.ERROR),
        ):
            self.client.get('/health/ready')

    def test_a_probe_that_breaks_is_still_an_error(self):
        with (
            mock.patch('config.health.ping_database', side_effect=RuntimeError('boom')),
            self.assertLogs(REQUEST_LOGGER, logging.DEBUG) as captured,
        ):
            self.client.raise_request_exception = False
            response = self.client.get('/health/ready')

        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.finished_line(captured)['level'], 'error')


class DatabaseTimeoutTests(TestCase):
    def test_connecting_gives_up_after_a_few_seconds(self):
        self.assertEqual(settings.DATABASES['default']['OPTIONS']['connect_timeout'], 5)
