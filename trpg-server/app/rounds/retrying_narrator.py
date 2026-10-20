# trpg-server/app/rounds/retrying_narrator.py

"""
서술이 실패하면 다시 시도하고, 그래도 안 되면 다음 모델로 넘어가는 서술자. Narrator 모양을 따른다.

안에 모델마다 서술자(LLMNarrator)를 하나씩 들고, 부를 차례대로 부른다.
부르는 것과 기록하는 것은 안의 서술자가 한다. 시도 하나하나가 따로 기록된다(app/ai/calls.py).
여기는 "언제 다시, 언제 넘어가고, 언제 그만두나"만 정한다.

정책.
  - 모델마다 두 번까지 부른다. 사이에 1~2초를 무작위로 쉰다.
    여러 테이블이 함께 실패해도 다시 부르는 때가 흩어진다.
  - 공급자가 "이만큼 뒤에 다시 하라"고 알려 주면(Retry-After, 429·503) 적어도 그만큼 쉬고 같은 모델로 다시 부른다.
    다만 MAX_RETRY_AFTER_SECONDS(20초)보다 길면 기다리지 않는다. 그 모델은 그만 부른다.
    서술 하나의 시간에 상한이 있어서, 오래 기다리면 다시 불러도 끝낼 시간이 없다.
  - 같은 요청을 다시 보내 봐야 소용없는 실패(요청이나 설정이 틀림)는 그 모델로 다시 부르지 않는다.
  - 다른 모델로 가도 소용없는 실패(서버가 꺼짐, 권한 없음)면 넘어가지 않고 그만둔다. 모델들은 같은 서버에 있다고 본다.
    한 등급에 창구가 다른 모델을 섞어 적으면 이 가정이 맞지 않는다. 섞어 적지 않는다(넘어가기는 모델 고르기에서 없앤다).
  - 같은 모델로 다시 부르는 것에는 예산이 있다(app/ai/retry_budget.py). 최근 1분의 첫 시도의 10%(적어도 3번)까지다.
    예산이 없으면 다시 부르지 않는다. 공급자가 내려가 모두가 실패할 때 재시도가 일을 두 배로 키우지 않게 한다.
  - 서술 하나에 쓰는 시간에 상한이 있다(NARRATION_BUDGET_SECONDS). 남은 시간이 한 번 부르는 시간보다 짧으면
    새로 부르지 않는다. 부르는 도중에 끊지 않으므로 시작한 호출은 모두 끝나고 기록된다.
끝내 실패하면 NarrationFailed 를 올린다. 이유는 마지막 실패의 것이다.
다만 어느 시도가 숨긴 진짜 이름을 써서 버려졌으면(secret_leaked), 끝내 실패할 때 그 이름을 호칭으로 가린 장면을 쓴다.
다시 불러 깨끗한 장면을 먼저 바라고, 안 되면 가린 것으로 이야기를 잇는다. 비밀은 어느 쪽이든 새지 않는다.
미리 보기는 안의 서술자에게 그대로 넘긴다. 시도마다 안의 서술자가 새로 시작한다.

서술자의 실패(ProviderError, NarrationError)만 다룬다. 그 밖의 예외는 버그다. 다시 시도하지 않고 그대로 올린다.

같은 모델로 다시 부른 것(round_narration_retries_total)과 다음 모델로 넘어간 것(ai_fallbacks_total)을 센다.
넘어간 것의 model 은 실패해 떠난 모델이다. 호출 하나하나는 기록장이 센다(app/ai_log/metered.py).
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.ai.provider import ProviderError
from app.ai.retry_budget import RetryBudget
from app.ai.routing import UNROUTABLE
from app.core.config import NARRATION_BUDGET_SECONDS
from app.observability.metrics import record_ai_fallback, record_narration_retry
from app.rounds.llm_narrator import PURPOSE, NarrationError, SecretLeaked
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Narrator, Preview

logger = logging.getLogger(__name__)

# 한 모델을 몇 번까지 부르나. 처음 한 번과 다시 한 번
ATTEMPTS_PER_MODEL = 2
# 다시 부르기 전에 쉬는 시간(초)의 범위. 이 안에서 무작위로 고른다
PAUSE_SECONDS = (1.0, 2.0)
# 공급자가 알려 준 대기 시간(Retry-After)을 이만큼까지만 따른다. 넘으면 그 모델로 다시 부르지 않는다
MAX_RETRY_AFTER_SECONDS = 20.0

# 같은 모델로 다시 불러도 소용없는 실패. 요청이나 설정이 틀렸다(404 는 그 이름의 모델이 없다).
# 모델 목록의 모델을 부를 수 없는 것(꺼짐, 키 없음, 창구의 코드 없음)도 같다(app/ai/routing.py)
NOT_FOR_THIS_MODEL = (
    frozenset({'status_400', 'status_401', 'status_403', 'status_404', 'status_422', 'no_story'}) | UNROUTABLE
)
# 다른 모델로 넘어가도 소용없는 실패. 서버가 꺼졌거나, 권한이 없거나, 요청에 이야기의 바탕이 없다
NOT_FOR_ANY_MODEL = frozenset({'unreachable', 'status_401', 'status_403', 'no_story'})


class NarrationFailed(Exception):
    """다시 시도하고 넘어가도 끝내 서술하지 못했다. reason 은 마지막 실패의 이유다(timeout, cut_off …)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def can_retry(reason: str) -> bool:
    """이 이유로 실패했을 때 같은 모델로 다시 불러 볼 만한가."""
    return reason not in NOT_FOR_THIS_MODEL


def can_fall_back(reason: str) -> bool:
    """이 이유로 실패했을 때 다음 모델로 넘어가 볼 만한가."""
    return reason not in NOT_FOR_ANY_MODEL


def settle(reason: str, redacted: str | None) -> str:
    """
    끝내 깨끗한 장면을 받지 못했을 때. 숨긴 이름을 가린 장면이 있으면 그것을 쓰고, 없으면 NarrationFailed.
    """
    if redacted is None:
        raise NarrationFailed(reason)
    logger.warning(
        '숨긴 이름을 가린 장면을 쓴다', extra={'result': 'secret_redacted', 'error_code': 'narration.secret_redacted'}
    )
    return redacted


def budget_key(narrator: Narrator) -> str:
    """재시도 예산을 세는 이름. 모델의 이름(RoutedNarrator.model)이다. 이름이 없는 서술자는 종류의 이름이다."""
    return getattr(narrator, 'model', type(narrator).__name__)


def random_pause() -> float:
    """다시 부르기 전에 쉴 시간(초). 범위 안에서 무작위다."""
    return random.uniform(*PAUSE_SECONDS)


@dataclass(frozen=True)
class RetryingNarrator:
    """
    다시 시도하고 넘어가는 서술자. narrators 는 모델마다 하나, 부를 차례대로다.

    attempt_timeout 은 한 번 부르는 시간의 상한이다(LLM_TIMEOUT_SECONDS). 남은 시간을 셀 때 쓴다.
    retry_budget 은 앱이 함께 쓰는 재시도 예산이다. 없으면(None) 예산 없이 attempts 번까지 부른다.
    pause, sleep, clock 은 테스트가 바꿔 꽂는다. 테스트가 실제로 쉬거나 실제 시계를 읽지 않게 한다.
    """

    narrators: list[Narrator]
    attempt_timeout: float
    budget: float = NARRATION_BUDGET_SECONDS
    attempts: int = ATTEMPTS_PER_MODEL
    pause: Callable[[], float] = random_pause
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    clock: Callable[[], float] = time.monotonic
    retry_budget: RetryBudget | None = None

    def wait_before_retry(self, error: ProviderError | NarrationError) -> float | None:
        """
        같은 모델로 다시 부르기 전에 쉴 초. 다시 부르지 않을 것이면 None.

        공급자가 대기 시간을 알려 줬으면 무작위로 쉴 시간과 견줘 긴 쪽이다. 상한을 넘으면 None 이다.
        """
        retry_after = getattr(error, 'retry_after', None)
        if retry_after is None:
            return self.pause()
        if retry_after > MAX_RETRY_AFTER_SECONDS:
            return None
        return max(self.pause(), retry_after)

    def note_first(self, narrator: Narrator) -> None:
        """그 모델에 첫 시도를 보낸다고 예산에 적는다."""
        if self.retry_budget is not None:
            self.retry_budget.note_request(budget_key(narrator))

    def may_retry(self, narrator: Narrator) -> bool:
        """그 모델로 다시 불러도 되는가. 예산이 없으면 경고를 남기고 False."""
        if self.retry_budget is None or self.retry_budget.try_retry(budget_key(narrator)):
            return True
        logger.warning(
            '재시도 예산이 다 되어 같은 모델로 다시 부르지 않는다',
            extra={'model': budget_key(narrator), 'result': 'retry_budget_exhausted'},
        )
        return False

    def has_time(self, started: float) -> bool:
        """started 부터 지금까지 쓴 시간에 한 번 더 부르는 시간을 더해도 상한 안인가."""
        return self.clock() - started + self.attempt_timeout <= self.budget

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        """차례대로 부른다. 처음 받은 장면을 돌려준다. 끝내 못 받으면 가린 장면을, 그것도 없으면 NarrationFailed."""
        started = self.clock()
        reason = 'no_model'
        redacted: str | None = None
        left: Narrator | None = None
        for narrator in self.narrators:
            if left is not None:
                record_ai_fallback(PURPOSE, budget_key(left))
            wait: float | None = None
            self.note_first(narrator)
            for number in range(self.attempts):
                if number > 0:
                    if not self.may_retry(narrator):
                        break
                    await self.sleep(wait)
                if not self.has_time(started):
                    return settle(reason, redacted)
                if number > 0:
                    record_narration_retry()
                try:
                    return await narrator.narrate(request, preview)
                except (ProviderError, NarrationError) as error:
                    reason = str(error)
                    wait = self.wait_before_retry(error)
                    if isinstance(error, SecretLeaked):
                        redacted = error.redacted
                if not can_retry(reason) or wait is None:
                    break
            if not can_fall_back(reason):
                break
            left = narrator
        return settle(reason, redacted)
