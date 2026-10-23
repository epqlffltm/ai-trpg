# chat-server/app/limits/setup.py

"""
설정을 보고 어디서 셀지 고르고, chat 의 제한들(Limits)을 만든다. 앱을 만들 때 한 번 부른다(app/main.py).

REDIS_URL 이 있으면 Redis 로, 없으면 서버 안의 메모리로 센다. Redis 는 DB 2 를 쓴다
(docs/architecture/services.md 의 "DB 와 Redis 의 한도").
"""

from dataclasses import dataclass
from datetime import timedelta

import redis.asyncio as redis

from app.core.config import Settings
from app.limits.attempts import AttemptLimit, Limiter
from app.limits.counters import Counter, MemoryCounter
from app.limits.redis_counter import RedisCounter, connect


@dataclass(frozen=True)
class Limits:
    """chat 의 제한들. 둘 다 사람마다 센다."""

    # 모델을 부르는 요청(말 보내기, 행동, 다시 생성, 이어서). 크레딧과 별개로, 짧은 시간에 몰아 보내는 것을 늦춘다
    generations: AttemptLimit
    # 모델을 부르지 않는 쓰기(대화 시작과 지우기, 모델과 가지 바꾸기, 고치기, 기억 메모). 청구하지 않아 넉넉하게 둔다
    writes: AttemptLimit


@dataclass(frozen=True)
class Limiting:
    """API 가 받는 것. 세고 막는 규칙과 제한들이다."""

    limiter: Limiter
    limits: Limits


def limits_from(settings: Settings) -> Limits:
    """설정의 값으로 제한들을 만든다."""
    return Limits(
        generations=AttemptLimit(
            'generations', settings.generation_limit, timedelta(seconds=settings.generation_window_seconds)
        ),
        writes=AttemptLimit('writes', settings.write_limit, timedelta(seconds=settings.write_window_seconds)),
    )


def build_redis(settings: Settings) -> redis.Redis | None:
    """REDIS_URL 이 있으면 Redis 클라이언트, 없으면 None. 앱이 꺼질 때 닫는다."""
    url = settings.redis_url.strip()
    return connect(url, settings.redis_timeout_seconds) if url else None


def build_counter(client: redis.Redis | None) -> Counter:
    """Redis 가 있으면 Redis 로, 없으면 메모리로 센다."""
    return RedisCounter(client) if client is not None else MemoryCounter()


def build_limiting(settings: Settings, client: redis.Redis | None) -> Limiting:
    """세고 막는 규칙과 제한들."""
    limiter = Limiter(build_counter(client), settings.limit_key_prefix, enabled=settings.limits_enabled)
    return Limiting(limiter, limits_from(settings))
