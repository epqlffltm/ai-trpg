# trpg-server/app/limits/setup.py

"""
설정을 보고 어디서 셀지 고르고, 게임 서버의 제한들(Limits)을 만든다. 앱을 만들 때 한 번 부른다(app/main.py).

REDIS_URL 이 있으면 Redis 로, 없으면 서버 안의 메모리로 센다.
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
    """게임 서버의 제한들."""

    # 로비의 비밀번호. 한 사람이 한 테이블에 틀린 수(맞히면 지운다)
    password_per_user: AttemptLimit
    # 로비의 비밀번호. 테이블 하나에 모든 사람이 틀린 수(지우지 않는다). 계정을 여럿 써서 맞히는 것을 막는다
    password_per_table: AttemptLimit
    # 채팅. 한 사람이 한 테이블에 쓴 수
    chat: AttemptLimit
    # 기록 내려받기(#617). 한 사람이 받은 수. 판 하나를 통째로 읽어 글로 바꾸므로 비싸다
    transcript: AttemptLimit


@dataclass(frozen=True)
class Limiting:
    """서비스가 받는 것. 세고 막는 규칙과 제한들이다."""

    limiter: Limiter
    limits: Limits


def limits_from(settings: Settings) -> Limits:
    """설정의 값으로 제한들을 만든다."""
    password_window = timedelta(seconds=settings.password_attempt_window_seconds)
    return Limits(
        password_per_user=AttemptLimit('table_password', settings.password_attempts_per_user, password_window),
        password_per_table=AttemptLimit('table_password_all', settings.password_attempts_per_table, password_window),
        chat=AttemptLimit('chat', settings.chat_messages_per_window, timedelta(seconds=settings.chat_window_seconds)),
        transcript=AttemptLimit(
            'transcript', settings.transcripts_per_window, timedelta(seconds=settings.transcript_window_seconds)
        ),
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
