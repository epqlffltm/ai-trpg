# auth-server/config/tests/test_redis_client.py

"""
Redis 앞의 차단기(config/redis_client.py)가 언제 열리고 닫히는지 확인한다.

테스트마다 차단기를 새로 만든다. 프로세스에 하나인 redis_breaker 는 건드리지 않는다.
"30초 뒤" 는 기다리지 않고, 열린 시간을 0초로 만든 차단기로 본다.
"""

from contextlib import suppress
from unittest.mock import Mock

import pybreaker
import redis
from django.test import SimpleTestCase

from config.redis_client import REDIS_FAILURES_BEFORE_OPEN, REDIS_OPEN_SECONDS, build_redis_breaker

LOGGER = 'config.redis_client'


def stuck_redis() -> None:
    """응답하지 않는 Redis 를 흉내 낸다."""
    raise redis.TimeoutError('Timeout reading from socket')


def answering_redis() -> str:
    return 'PONG'


def trip(breaker: pybreaker.CircuitBreaker) -> None:
    """연달아 실패시켜 차단기를 연다."""
    for _ in range(REDIS_FAILURES_BEFORE_OPEN):
        with suppress(redis.RedisError, pybreaker.CircuitBreakerError):
            breaker.call(stuck_redis)


class OpeningTests(SimpleTestCase):
    def test_opens_after_failures_in_a_row(self):
        breaker = build_redis_breaker()

        for _ in range(REDIS_FAILURES_BEFORE_OPEN - 1):
            with self.assertRaises(redis.TimeoutError):
                breaker.call(stuck_redis)
            self.assertEqual(breaker.current_state, pybreaker.STATE_CLOSED)

        # 열리는 그 호출은 CircuitBreakerError 로 바뀌어 나온다
        with self.assertRaises(pybreaker.CircuitBreakerError):
            breaker.call(stuck_redis)
        self.assertEqual(breaker.current_state, pybreaker.STATE_OPEN)

    def test_a_success_starts_the_count_again(self):
        breaker = build_redis_breaker()

        for _ in range(3):
            for _ in range(REDIS_FAILURES_BEFORE_OPEN - 1):
                with self.assertRaises(redis.TimeoutError):
                    breaker.call(stuck_redis)
            breaker.call(answering_redis)

        self.assertEqual(breaker.current_state, pybreaker.STATE_CLOSED)

    def test_errors_that_are_not_from_redis_are_not_counted(self):
        breaker = build_redis_breaker()

        def broken_code():
            raise TypeError('코드의 실수')

        for _ in range(REDIS_FAILURES_BEFORE_OPEN * 2):
            with self.assertRaises(TypeError):
                breaker.call(broken_code)

        self.assertEqual(breaker.current_state, pybreaker.STATE_CLOSED)

    def test_open_breaker_does_not_ask_redis(self):
        breaker = build_redis_breaker()
        trip(breaker)
        command = Mock(return_value='PONG')

        with self.assertRaises(pybreaker.CircuitBreakerError):
            breaker.call(command)

        command.assert_not_called()


class TrialTests(SimpleTestCase):
    def test_after_the_open_time_one_success_closes_it(self):
        breaker = build_redis_breaker(open_seconds=0)
        trip(breaker)

        self.assertEqual(breaker.call(answering_redis), 'PONG')
        self.assertEqual(breaker.current_state, pybreaker.STATE_CLOSED)

    def test_a_failed_trial_opens_it_again(self):
        breaker = build_redis_breaker(open_seconds=0)
        trip(breaker)

        with self.assertRaises(pybreaker.CircuitBreakerError):
            breaker.call(stuck_redis)

        self.assertEqual(breaker.current_state, pybreaker.STATE_OPEN)

    def test_the_open_time_is_thirty_seconds(self):
        self.assertEqual(build_redis_breaker().reset_timeout, REDIS_OPEN_SECONDS)
        self.assertEqual(REDIS_OPEN_SECONDS, 30)


class LogTests(SimpleTestCase):
    def test_opening_is_logged_once(self):
        breaker = build_redis_breaker()

        with self.assertLogs(LOGGER, level='WARNING') as logs:
            trip(breaker)

        self.assertEqual(len(logs.output), 1)
        self.assertIn(f'{REDIS_OPEN_SECONDS}초', logs.output[0])

    def test_requests_while_open_are_not_logged(self):
        breaker = build_redis_breaker()
        trip(breaker)

        with self.assertNoLogs(LOGGER):
            for _ in range(10):
                with self.assertRaises(pybreaker.CircuitBreakerError):
                    breaker.call(answering_redis)

    def test_recovery_is_logged(self):
        breaker = build_redis_breaker(open_seconds=0)
        trip(breaker)

        with self.assertLogs(LOGGER, level='INFO') as logs:
            breaker.call(answering_redis)

        self.assertEqual(len(logs.output), 1)
        self.assertIn('닫았다', logs.output[0])

    def test_closing_by_hand_is_not_logged(self):
        # 테스트가 차단기를 처음 상태로 돌릴 때(close)는 회복이 아니다
        breaker = build_redis_breaker()
        trip(breaker)

        with self.assertNoLogs(LOGGER):
            breaker.close()
