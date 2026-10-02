# auth-server/accounts/attempt_limits.py

"""
시도 횟수 제한. "누가 정해진 시간 안에 몇 번 시도했는가" 를 Redis 에 센다.

보조 장치다. 인증의 1차 방어(비밀번호, 이메일 코드, 코드의 오답 제한)는 전부 PostgreSQL 에 있다.
여기는 그 앞에서 시도의 속도를 늦출 뿐이다. 그래서 Redis 가 죽으면 막지 않고 통과시킨다.
Redis 장애가 로그인 장애가 되어서는 안 된다.

HTTP 를 모른다. 무엇을 기준으로 셀지(IP, 계정)는 부르는 쪽이 정해 문자열로 넘긴다.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import timedelta

import redis
from django.conf import settings

from config.redis_client import get_redis

logger = logging.getLogger(__name__)

# 횟수를 올리고, 처음 올린 것이면 유효 시간을 건다. 남은 시간도 함께 돌려준다.
#
# 이 셋을 따로 보내면 사이에 틈이 생긴다. 횟수를 올린 직후 서버가 죽으면
# 유효 시간이 없는 키가 남아, 그 대상은 영영 막힌다.
# Lua 스크립트는 Redis 안에서 한 덩어리로 실행되어 중간에 끊기지 않는다.
INCREMENT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


@dataclass(frozen=True)
class AttemptLimit:
    """
    제한 하나. "window 동안 max_attempts 번까지".

    구간은 첫 시도에서 시작해 window 뒤에 끝난다(고정 구간).
    구간의 경계에 걸치면 짧은 시간에 최대 2배까지 허용될 수 있다. 속도를 늦추는 용도에는 충분하다.
    """

    # Redis 키에 들어간다. 제한마다 달라야 서로의 횟수가 섞이지 않는다
    name: str
    max_attempts: int
    window: timedelta


class TooManyAttemptsError(Exception):
    """정해진 시간 안에 허용된 횟수를 넘었다. 언제 다시 시도할 수 있는지를 담는다."""

    def __init__(self, retry_after: timedelta):
        super().__init__()
        self.retry_after = retry_after


def count_attempt(limit: AttemptLimit, subject: str) -> None:
    """
    시도 한 번을 세고, 허용된 횟수를 넘었으면 TooManyAttemptsError 를 낸다.

    성공이든 실패든 모든 시도를 셀 때 쓴다(가입 요청, 재설정 요청 등).
    """
    if not settings.ATTEMPT_LIMITS_ENABLED:
        return
    try:
        count, seconds_left = _increment(limit, subject)
    except redis.RedisError as exc:
        _log_redis_failure(exc)
        return
    if count > limit.max_attempts:
        raise TooManyAttemptsError(_retry_after(limit, seconds_left))


def ensure_not_blocked(limit: AttemptLimit, subject: str) -> None:
    """
    이미 허용된 횟수를 채웠으면 TooManyAttemptsError 를 낸다. 횟수는 올리지 않는다.

    실패한 시도만 셀 때 쓴다. 먼저 이것으로 막혔는지 보고, 시도가 실패하면 count_failure 를 부른다.
    """
    if not settings.ATTEMPT_LIMITS_ENABLED:
        return
    try:
        count, seconds_left = _read(limit, subject)
    except redis.RedisError as exc:
        _log_redis_failure(exc)
        return
    if count >= limit.max_attempts:
        raise TooManyAttemptsError(_retry_after(limit, seconds_left))


def count_failure(limit: AttemptLimit, subject: str) -> None:
    """실패한 시도 한 번을 센다. 예외를 내지 않는다. 막는 것은 다음 시도의 ensure_not_blocked 가 한다."""
    if not settings.ATTEMPT_LIMITS_ENABLED:
        return
    try:
        _increment(limit, subject)
    except redis.RedisError as exc:
        _log_redis_failure(exc)


def clear_attempts(limit: AttemptLimit, subject: str) -> None:
    """세던 횟수를 지운다. 시도가 성공했을 때 부른다."""
    if not settings.ATTEMPT_LIMITS_ENABLED:
        return
    try:
        get_redis().delete(_key(limit, subject))
    except redis.RedisError as exc:
        _log_redis_failure(exc)


def _increment(limit: AttemptLimit, subject: str) -> tuple[int, int]:
    """횟수를 하나 올리고 (횟수, 구간이 끝나기까지 남은 초) 를 돌려준다."""
    window_seconds = int(limit.window.total_seconds())
    count, seconds_left = get_redis().eval(INCREMENT_SCRIPT, 1, _key(limit, subject), window_seconds)
    return int(count), int(seconds_left)


def _read(limit: AttemptLimit, subject: str) -> tuple[int, int]:
    """횟수를 올리지 않고 (횟수, 남은 초) 를 읽는다. 센 적이 없으면 (0, 0) 이다."""
    key = _key(limit, subject)
    # 두 명령을 한 번에 보낸다. 따로 보내면 사이에 키가 만료될 수 있다
    pipeline = get_redis().pipeline()
    pipeline.get(key)
    pipeline.ttl(key)
    count, seconds_left = pipeline.execute()
    return int(count or 0), max(int(seconds_left), 0)


def _key(limit: AttemptLimit, subject: str) -> str:
    """
    Redis 키를 만든다.

    대상(IP, 아이디, 이메일)을 그대로 넣지 않고 해시한다. 키는 Redis 의 로그나
    모니터링 도구에 그대로 보인다. 이메일 주소 같은 개인정보가 거기 남지 않게 한다.
    길이와 글자도 일정해진다.
    """
    digest = hashlib.sha256(subject.encode()).hexdigest()[:32]
    return f'{settings.ATTEMPT_LIMIT_KEY_PREFIX}:{limit.name}:{digest}'


def _retry_after(limit: AttemptLimit, seconds_left: int) -> timedelta:
    """
    다시 시도할 수 있을 때까지의 시간.

    남은 시간이 0 이하로 읽히는 드문 경우(키가 방금 만료됨)에는 1초로 답한다.
    """
    return timedelta(seconds=max(seconds_left, 1))


def _log_redis_failure(error: Exception) -> None:
    """
    Redis 를 쓸 수 없었음을 남긴다. 요청은 막지 않고 통과시킨다.

    경고로 남겨야 한다. 조용히 넘어가면 제한이 꺼져 있다는 것을 아무도 모른다.
    """
    logger.warning('시도 횟수를 셀 수 없어 제한 없이 통과시켰다: %s: %s', type(error).__name__, error)
