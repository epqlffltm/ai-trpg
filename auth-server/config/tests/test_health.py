# auth-server/config/tests/test_health.py

"""
상태 확인 주소(config/health.py)를 실제 요청으로 확인한다.

규격(저장소 루트의 docs/observability.md)이 정한 것: 본문은 정확히 {"status": ...} 하나, health 는 DB 를 보지 않는다,
readiness 는 DB 에 닿지 않으면 503 이고 이유를 응답에 싣지 않는다.
"""

from unittest import mock

from django.conf import settings
from django.db import OperationalError
from django.test import TestCase

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

    def test_health_takes_only_get(self):
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

    def test_ready_takes_only_get(self):
        response = self.client.post('/health/ready')

        self.assertEqual(response.status_code, 405)


class DatabaseTimeoutTests(TestCase):
    def test_connecting_gives_up_after_a_few_seconds(self):
        self.assertEqual(settings.DATABASES['default']['OPTIONS']['connect_timeout'], 5)
