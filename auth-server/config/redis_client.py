# auth-server/config/redis_client.py

"""
Redis 연결과 그 앞의 차단기.

Redis 에는 없어도 서비스가 도는 보조 장치(시도 횟수)만 둔다.
그래서 여기의 연결은 "빨리 실패하는" 쪽으로 잡는다. Redis 가 응답하지 않을 때
요청이 그것을 기다리느라 느려지면, 보조 장치가 서비스를 끌어내리는 꼴이 된다.

빨리 실패해도 명령마다 REDIS_TIMEOUT_SECONDS 를 기다린다. 로그인 한 번이 Redis 를 서너 번 부르므로
Redis 가 멈추면 로그인마다 그만큼 늦어진다. 그래서 연달아 실패하면 차단기(redis_breaker)를 열어
한동안 Redis 에 묻지 않는다(#26). 차단기의 상태는 프로세스마다 따로 있다. 죽은 Redis 에 둘 수 없다.

차단기는 pybreaker 다. call() 이 명령이 끝날 때까지 잠금을 쥐어, 한 프로세스의 Redis 명령이 한 줄로 선다.
gunicorn 의 sync 워커는 프로세스에 스레드가 하나라 손해가 없다. 스레드 워커(gthread)로 바꾸면 이것을 다시 본다.
"""

import logging
from functools import lru_cache

import pybreaker
import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Redis 에 연결하거나 응답을 기다리는 최대 시간(초).
# 같은 기기나 같은 망에 있는 Redis 는 보통 1밀리초 안에 응답한다. 이만큼 기다려도 안 오면 죽은 것으로 본다
REDIS_TIMEOUT_SECONDS = 0.2

# 연달아 이만큼 실패하면 차단기를 연다. 한 번의 실패(잠깐의 끊김)로는 열지 않는다
REDIS_FAILURES_BEFORE_OPEN = 3

# 열린 차단기는 이 시간(초) 동안 Redis 에 묻지 않는다. 지나면 요청 하나로 다시 시험한다.
# Redis 가 살아난 뒤 시도 횟수 제한이 다시 켜지기까지 최대 이만큼 걸린다
REDIS_OPEN_SECONDS = 30


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    """
    Redis 클라이언트를 돌려준다. 프로세스마다 하나만 만들어 계속 쓴다.

    만드는 시점에는 접속하지 않는다. 처음 명령을 보낼 때 접속한다.
    그래서 Redis 가 죽어 있어도 서버는 뜬다.
    """
    return redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
        # 응답을 bytes 가 아니라 str 로 받는다
        decode_responses=True,
    )


def is_not_redis_error(error: BaseException) -> bool:
    """
    Redis 의 오류가 아닌 예외인가. 차단기가 세지 않는 예외를 고른다.

    pybreaker 는 기본으로 모든 예외를 실패로 센다. 코드의 실수(TypeError 같은)는 Redis 가 아프다는 신호가 아니다.
    """
    return not isinstance(error, redis.RedisError)


def log_breaker_change(old_state: str | None, new_state: str, open_seconds: float) -> None:
    """
    차단기의 상태가 바뀐 것을 남긴다. 열릴 때와, 시험이 성공해 닫힐 때만 남긴다.

    열린 동안의 요청마다 남기지 않는다. Redis 가 계속 죽어 있으면 시험이 실패할 때마다 다시 열리므로
    open_seconds 마다 한 줄씩 남는다. 그것으로 아직 죽어 있다는 것을 안다.
    """
    if new_state == pybreaker.STATE_OPEN:
        logger.warning('Redis 를 쓸 수 없어 차단기를 열었다. %s초 동안 시도 횟수 제한 없이 통과시킨다', open_seconds)
    elif new_state == pybreaker.STATE_CLOSED and old_state == pybreaker.STATE_HALF_OPEN:
        logger.info('Redis 가 돌아와 차단기를 닫았다. 시도 횟수 제한을 다시 쓴다')


class BreakerLogListener(pybreaker.CircuitBreakerListener):
    """차단기의 상태가 바뀔 때 log_breaker_change 를 부른다."""

    def state_change(self, cb: pybreaker.CircuitBreaker, old_state, new_state) -> None:
        log_breaker_change(old_state.name if old_state else None, new_state.name, cb.reset_timeout)


def build_redis_breaker(open_seconds: float = REDIS_OPEN_SECONDS) -> pybreaker.CircuitBreaker:
    """
    Redis 앞의 차단기를 만든다.

    열린 동안 부르면 Redis 에 묻지 않고 pybreaker.CircuitBreakerError 를 낸다. 부르는 쪽은 그것을
    Redis 오류와 같이 "쓸 수 없음" 으로 다룬다. 열리는 그 호출도 CircuitBreakerError 로 바뀌어 나온다.
    """
    return pybreaker.CircuitBreaker(
        fail_max=REDIS_FAILURES_BEFORE_OPEN,
        reset_timeout=open_seconds,
        exclude=[is_not_redis_error],
        listeners=[BreakerLogListener()],
        name='redis',
    )


# 프로세스마다 하나. Redis 를 부르는 곳은 모두 이것을 거친다(redis_breaker.call(함수, 인자...))
redis_breaker = build_redis_breaker()
