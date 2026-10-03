# auth-server/accounts/tests/test_attempt_limits.py

"""
시도 횟수 제한을 검증한다. 실제 Redis 에서 돈다.

다른 테스트에서는 제한이 꺼져 있다. 이 파일은 켜고 돈다.
"""

from datetime import timedelta
from unittest.mock import patch

import redis
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from accounts.attempt_limits import (
    AttemptLimit,
    TooManyAttemptsError,
    _key,
    clear_attempts,
    count_attempt,
    count_failure,
    ensure_not_blocked,
)
from accounts.tests.helpers import delete_attempt_keys
from config.redis_client import get_redis

LIMIT = AttemptLimit(name='test-limit', max_attempts=3, window=timedelta(minutes=10))
OTHER_LIMIT = AttemptLimit(name='test-other', max_attempts=3, window=timedelta(minutes=10))


@override_settings(ATTEMPT_LIMITS_ENABLED=True)
class AttemptLimitTestCase(SimpleTestCase):
    """DB 를 쓰지 않는다. Redis 만 쓴다."""

    def setUp(self):
        delete_attempt_keys()
        self.addCleanup(delete_attempt_keys)

    def key_for(self, subject: str) -> str:
        return _key(LIMIT, subject)

    def ttl_of(self, subject: str) -> int:
        return get_redis().ttl(self.key_for(subject))


class CountAttemptTests(AttemptLimitTestCase):
    def test_allows_up_to_the_limit(self):
        for _ in range(LIMIT.max_attempts):
            count_attempt(LIMIT, 'someone')

    def test_blocks_the_attempt_over_the_limit(self):
        for _ in range(LIMIT.max_attempts):
            count_attempt(LIMIT, 'someone')

        with self.assertRaises(TooManyAttemptsError) as caught:
            count_attempt(LIMIT, 'someone')

        # 구간이 끝날 때까지 기다리라고 알려 준다
        self.assertGreater(caught.exception.retry_after, timedelta(minutes=9))
        self.assertLessEqual(caught.exception.retry_after, LIMIT.window)

    def test_only_the_first_blocked_attempt_is_marked(self):
        for _ in range(LIMIT.max_attempts):
            count_attempt(LIMIT, 'someone')

        with self.assertRaises(TooManyAttemptsError) as first:
            count_attempt(LIMIT, 'someone')
        with self.assertRaises(TooManyAttemptsError) as second:
            count_attempt(LIMIT, 'someone')

        # "막혔다" 는 기록을 구간마다 한 번만 남기는 데 쓴다
        self.assertTrue(first.exception.first_block)
        self.assertFalse(second.exception.first_block)

    def test_subjects_are_counted_separately(self):
        for _ in range(LIMIT.max_attempts):
            count_attempt(LIMIT, 'someone')

        # 다른 대상은 영향을 받지 않는다
        count_attempt(LIMIT, 'someone-else')

    def test_limits_are_counted_separately(self):
        for _ in range(LIMIT.max_attempts):
            count_attempt(LIMIT, 'someone')

        # 같은 대상이라도 다른 제한의 횟수와 섞이지 않는다
        count_attempt(OTHER_LIMIT, 'someone')

    def test_counter_expires_with_the_window(self):
        count_attempt(LIMIT, 'someone')

        seconds_left = self.ttl_of('someone')

        # 유효 시간이 없는 키(-1)가 남으면 그 대상은 영영 막힌다
        self.assertGreater(seconds_left, 0)
        self.assertLessEqual(seconds_left, LIMIT.window.total_seconds())

    def test_later_attempts_do_not_extend_the_window(self):
        count_attempt(LIMIT, 'someone')
        get_redis().expire(self.key_for('someone'), 100)

        count_attempt(LIMIT, 'someone')

        # 구간은 첫 시도에 고정된다. 계속 두드린다고 막힌 시간이 늘어나지 않는다
        self.assertLessEqual(self.ttl_of('someone'), 100)

    def test_allows_again_after_the_window(self):
        for _ in range(LIMIT.max_attempts):
            count_attempt(LIMIT, 'someone')
        # 구간이 끝난 것처럼 키를 없앤다
        get_redis().delete(self.key_for('someone'))

        count_attempt(LIMIT, 'someone')

    def test_key_does_not_contain_the_subject(self):
        count_attempt(LIMIT, 'someone@example.com')

        keys = list(get_redis().scan_iter(match=f'{settings.ATTEMPT_LIMIT_KEY_PREFIX}:*'))

        # 키는 Redis 의 로그와 모니터링 도구에 보인다. 이메일 주소가 그대로 들어가면 안 된다
        self.assertEqual(len(keys), 1)
        self.assertNotIn('someone', keys[0])
        self.assertIn(LIMIT.name, keys[0])


class FailureCountingTests(AttemptLimitTestCase):
    """실패한 시도만 세는 쓰임. 막혔는지 먼저 보고, 실패하면 센다."""

    def test_not_blocked_before_any_failure(self):
        ensure_not_blocked(LIMIT, 'someone')

    def test_tells_when_a_failure_starts_the_block(self):
        results = [count_failure(LIMIT, 'someone') for _ in range(LIMIT.max_attempts + 1)]

        # 허용된 횟수를 막 채운 실패에서만 True 다. 그 뒤의 실패는 이미 막힌 뒤다
        self.assertEqual(results, [False, False, True, False])

    def test_blocked_once_failures_reach_the_limit(self):
        for _ in range(LIMIT.max_attempts):
            ensure_not_blocked(LIMIT, 'someone')
            count_failure(LIMIT, 'someone')

        with self.assertRaises(TooManyAttemptsError) as caught:
            ensure_not_blocked(LIMIT, 'someone')

        self.assertGreater(caught.exception.retry_after, timedelta(0))

    def test_checking_does_not_count(self):
        for _ in range(LIMIT.max_attempts * 3):
            ensure_not_blocked(LIMIT, 'someone')

        # 확인만으로는 횟수가 오르지 않는다. 성공한 시도가 스스로를 막지 않는다
        ensure_not_blocked(LIMIT, 'someone')

    def test_counting_a_failure_never_raises(self):
        for _ in range(LIMIT.max_attempts * 2):
            count_failure(LIMIT, 'someone')

    def test_clearing_unblocks(self):
        for _ in range(LIMIT.max_attempts):
            count_failure(LIMIT, 'someone')

        clear_attempts(LIMIT, 'someone')

        ensure_not_blocked(LIMIT, 'someone')


class RedisDownTests(AttemptLimitTestCase):
    """Redis 를 쓸 수 없으면 막지 않고 통과시킨다."""

    def redis_down(self):
        return patch(
            'accounts.attempt_limits.get_redis',
            side_effect=redis.ConnectionError('Connection refused'),
        )

    def test_every_operation_lets_the_request_through(self):
        with self.redis_down(), self.assertLogs('accounts.attempt_limits', level='WARNING'):
            for _ in range(LIMIT.max_attempts * 2):
                count_attempt(LIMIT, 'someone')
                ensure_not_blocked(LIMIT, 'someone')
                count_failure(LIMIT, 'someone')
                clear_attempts(LIMIT, 'someone')

    def test_failure_is_logged_so_someone_notices(self):
        with self.redis_down(), self.assertLogs('accounts.attempt_limits', level='WARNING') as logs:
            count_attempt(LIMIT, 'someone')

        # 조용히 넘어가면 제한이 꺼져 있다는 것을 아무도 모른다
        self.assertIn('ConnectionError', logs.output[0])

    def test_timeout_is_treated_like_any_other_failure(self):
        with patch('accounts.attempt_limits.get_redis', side_effect=redis.TimeoutError('timed out')):
            with self.assertLogs('accounts.attempt_limits', level='WARNING'):
                count_attempt(LIMIT, 'someone')


class DisabledTests(SimpleTestCase):
    """제한이 꺼져 있으면 Redis 에 가지 않는다. 다른 테스트가 이 상태로 돈다."""

    def test_nothing_touches_redis(self):
        with patch('accounts.attempt_limits.get_redis') as client:
            for _ in range(LIMIT.max_attempts * 2):
                count_attempt(LIMIT, 'someone')
                ensure_not_blocked(LIMIT, 'someone')
                count_failure(LIMIT, 'someone')
                clear_attempts(LIMIT, 'someone')

        client.assert_not_called()
