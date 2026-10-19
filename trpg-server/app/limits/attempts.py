# trpg-server/app/limits/attempts.py

"""
제한 하나(AttemptLimit)와, 세고 막는 규칙(Limiter).

구간은 첫 시도에서 시작해 window 뒤에 끝난다(고정 구간). 경계에 걸치면 짧은 시간에 두 배까지 될 수 있다.
속도를 늦추는 용도에는 충분하다. 인증 서버와 같다.

세는 방법이 둘이다.
  - 모든 시도를 센다(count_attempt). 채팅처럼 성공한 것도 세는 곳.
  - 실패만 센다(ensure_not_blocked → 시도 → 실패면 count_failure, 성공이면 clear). 비밀번호처럼 맞히면 지워 주는 곳.

세는 곳(Redis)에 닿지 못했을 때도 둘이다. 어느 쪽인지는 함수의 이름이 말한다.
  - 막는다(ensure_not_blocked): LimitsUnavailable(503). 비밀번호처럼 막지 않으면 무차별 대입이 열리는 곳.
  - 통과시킨다(count_attempt): 경고만 남긴다. 채팅처럼 막아서 잃는 것이 더 큰 곳.
경고는 남겨야 한다. 조용히 넘어가면 제한이 꺼져 있다는 것을 아무도 모른다.

HTTP 를 모른다. 무엇을 기준으로 셀지(사람, 테이블)는 부르는 쪽이 정해 글자로 넘긴다. 키에는 해시해서 넣는다.
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


class LimitsUnavailable(Exception):
    """세는 곳에 닿지 못해, 막아야 하는 시도를 막았다."""


def retry_after(tally: Tally) -> int:
    """다시 할 수 있을 때까지의 초. 키가 방금 만료돼 0 으로 읽히면 1 초다."""
    return max(tally.seconds_left, 1)


def warn_unavailable(limit: AttemptLimit, blocked: bool) -> None:
    """세는 곳에 닿지 못한 것을 남긴다. blocked 면 막았고, 아니면 제한 없이 통과시켰다."""
    logger.warning(
        '시도 횟수를 셀 수 없습니다',
        extra={'limit': limit.name, 'blocked': blocked, 'error_code': UNAVAILABLE_ERROR_CODE},
    )


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
        """
        키를 만든다. 대상(사람과 테이블의 번호)을 그대로 넣지 않고 해시한다.

        키는 Redis 의 로그와 모니터링 도구에 그대로 보인다. 길이와 글자도 일정해진다.
        """
        digest = hashlib.sha256(subject.encode()).hexdigest()[:32]
        return f'{self.prefix}:{limit.name}:{digest}'

    async def count_attempt(self, limit: AttemptLimit, subject: str) -> None:
        """
        시도 한 번을 세고, 허용된 횟수를 넘었으면 TooManyAttempts.

        세는 곳에 닿지 못하면 경고를 남기고 통과시킨다.
        """
        if not self.enabled:
            return
        try:
            tally = await self.counter.hit(self.key(limit, subject), int(limit.window.total_seconds()))
        except CounterUnavailable:
            warn_unavailable(limit, blocked=False)
            return
        if tally.count > limit.max_attempts:
            raise TooManyAttempts(retry_after(tally))

    async def ensure_not_blocked(self, limit: AttemptLimit, subject: str) -> None:
        """
        이미 허용된 횟수만큼 실패했으면 TooManyAttempts. 수를 올리지 않는다.

        세는 곳에 닿지 못하면 막는다(LimitsUnavailable). 실패를 셀 수 없으면 무한히 시도할 수 있기 때문이다.
        """
        if not self.enabled:
            return
        try:
            tally = await self.counter.read(self.key(limit, subject))
        except CounterUnavailable as error:
            warn_unavailable(limit, blocked=True)
            raise LimitsUnavailable from error
        if tally.count >= limit.max_attempts:
            raise TooManyAttempts(retry_after(tally))

    async def count_failure(self, limit: AttemptLimit, subject: str) -> None:
        """
        실패 한 번을 센다. 막는 것은 다음 시도의 ensure_not_blocked 가 한다.

        세는 곳에 닿지 못하면 경고만 남긴다. 다음 시도의 ensure_not_blocked 도 닿지 못해 막힌다.
        """
        if not self.enabled:
            return
        try:
            await self.counter.hit(self.key(limit, subject), int(limit.window.total_seconds()))
        except CounterUnavailable:
            warn_unavailable(limit, blocked=False)

    async def clear(self, limit: AttemptLimit, subject: str) -> None:
        """센 수를 지운다. 시도가 성공했을 때 부른다. 닿지 못하면 경고만 남긴다(수는 시간이 지나면 사라진다)."""
        if not self.enabled:
            return
        try:
            await self.counter.clear(self.key(limit, subject))
        except CounterUnavailable:
            warn_unavailable(limit, blocked=False)
