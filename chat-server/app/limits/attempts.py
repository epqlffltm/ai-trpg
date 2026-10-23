# chat-server/app/limits/attempts.py

"""
제한 하나(AttemptLimit)와, 세고 막는 규칙(Limiter).

구간은 첫 시도에서 시작해 window 뒤에 끝난다(고정 구간). 경계에 걸치면 짧은 시간에 두 배까지 될 수 있다.
속도를 늦추는 용도에는 충분하다. 인증 서버, 게임 서버와 같다.

모든 시도를 센다. 세는 곳(Redis)에 닿지 못하면 통과시키고 경고만 남긴다(대화를 막아서 잃는 것이 더 크다).
경고는 남겨야 한다. 조용히 넘어가면 제한이 꺼져 있다는 것을 아무도 모른다.
HTTP 를 모른다. 무엇을 기준으로 셀지(사람)는 부르는 쪽이 글자로 넘긴다. 키에는 해시해서 넣는다.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import timedelta

from app.limits.counters import Counter, CounterUnavailable, Tally

logger = logging.getLogger(__name__)

# 세는 곳에 닿지 못했을 때의 오류 코드. 정해진 이름이다(docs/observability.md)
UNAVAILABLE_ERROR_CODE = 'limits.unavailable'


@dataclass(frozen=True)
class AttemptLimit:
    """제한 하나. "window 동안 max_attempts 번까지". name 은 키에 들어간다. 제한마다 달라야 수가 섞이지 않는다."""

    name: str
    max_attempts: int
    window: timedelta


class TooManyAttempts(Exception):
    """허용된 횟수를 넘었다. retry_after 초 뒤에 다시 할 수 있다."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(retry_after)
        self.retry_after = retry_after


def retry_after(tally: Tally) -> int:
    """다시 할 수 있을 때까지의 초. 키가 방금 만료돼 0 으로 읽히면 1 초다."""
    return max(tally.seconds_left, 1)


@dataclass(frozen=True)
class Limiter:
    """
    세고 막는 규칙. counter 는 세는 곳, prefix 는 키의 앞부분이다(다른 서버, 테스트와 섞이지 않게).

    enabled 가 거짓이면 아무것도 세지 않고 막지 않는다. 테스트가 끈다(제한을 보는 테스트만 켠다).
    """

    counter: Counter
    prefix: str
    enabled: bool = True

    def key(self, limit: AttemptLimit, subject: str) -> str:
        """키를 만든다. 대상(사람의 번호)을 그대로 넣지 않고 해시한다. 키는 Redis 의 로그와 모니터링에 보인다."""
        digest = hashlib.sha256(subject.encode()).hexdigest()[:32]
        return f'{self.prefix}:{limit.name}:{digest}'

    async def count_attempt(self, limit: AttemptLimit, subject: str) -> None:
        """시도 한 번을 세고, 허용된 횟수를 넘었으면 TooManyAttempts. 세는 곳에 닿지 못하면 경고를 남기고 통과시킨다."""
        if not self.enabled:
            return
        try:
            tally = await self.counter.hit(self.key(limit, subject), int(limit.window.total_seconds()))
        except CounterUnavailable:
            logger.warning(
                '요청 수를 셀 수 없습니다',
                extra={'limit': limit.name, 'blocked': False, 'error_code': UNAVAILABLE_ERROR_CODE},
            )
            return
        if tally.count > limit.max_attempts:
            raise TooManyAttempts(retry_after(tally))
