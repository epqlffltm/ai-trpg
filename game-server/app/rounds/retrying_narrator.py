# game-server/app/rounds/retrying_narrator.py

"""
서술이 실패하면 다시 시도하고, 그래도 안 되면 다음 모델로 넘어가는 서술자. Narrator 모양을 따른다.

안에 모델마다 서술자(LLMNarrator)를 하나씩 들고, 부를 차례대로 부른다.
부르는 것과 기록하는 것은 안의 서술자가 한다. 시도 하나하나가 따로 기록된다(app/ai/calls.py).
여기는 "언제 다시, 언제 넘어가고, 언제 그만두나"만 정한다.

정책.
  - 모델마다 두 번까지 부른다. 사이에 1~2초를 무작위로 쉰다.
    여러 테이블이 함께 실패해도 다시 부르는 때가 흩어진다.
  - 같은 요청을 다시 보내 봐야 소용없는 실패(요청이나 설정이 틀림)는 그 모델로 다시 부르지 않는다.
  - 다른 모델로 가도 소용없는 실패(서버가 꺼짐, 권한 없음)면 넘어가지 않고 그만둔다. 모델들은 같은 서버에 있다.
  - 서술 하나에 쓰는 시간에 상한이 있다(NARRATION_BUDGET_SECONDS). 남은 시간이 한 번 부르는 시간보다 짧으면
    새로 부르지 않는다. 부르는 도중에 끊지 않으므로 시작한 호출은 모두 끝나고 기록된다.
끝내 실패하면 NarrationFailed 를 올린다. 이유는 마지막 실패의 것이다.
미리 보기는 안의 서술자에게 그대로 넘긴다. 시도마다 안의 서술자가 새로 시작한다.

서술자의 실패(ProviderError, NarrationError)만 다룬다. 그 밖의 예외는 버그다. 다시 시도하지 않고 그대로 올린다.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.ai.provider import ProviderError
from app.core.config import NARRATION_BUDGET_SECONDS
from app.rounds.llm_narrator import NarrationError
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Narrator, Preview

# 한 모델을 몇 번까지 부르나. 처음 한 번과 다시 한 번
ATTEMPTS_PER_MODEL = 2
# 다시 부르기 전에 쉬는 시간(초)의 범위. 이 안에서 무작위로 고른다
PAUSE_SECONDS = (1.0, 2.0)

# 같은 모델로 다시 불러도 소용없는 실패. 요청이나 설정이 틀렸다(404 는 그 이름의 모델이 없다)
NOT_FOR_THIS_MODEL = frozenset({'status_400', 'status_401', 'status_403', 'status_404', 'status_422', 'no_story'})
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


def random_pause() -> float:
    """다시 부르기 전에 쉴 시간(초). 범위 안에서 무작위다."""
    return random.uniform(*PAUSE_SECONDS)


@dataclass(frozen=True)
class RetryingNarrator:
    """
    다시 시도하고 넘어가는 서술자. narrators 는 모델마다 하나, 부를 차례대로다.

    attempt_timeout 은 한 번 부르는 시간의 상한이다(LLM_TIMEOUT_SECONDS). 남은 시간을 셀 때 쓴다.
    pause, sleep, clock 은 테스트가 바꿔 꽂는다. 테스트가 실제로 쉬거나 실제 시계를 읽지 않게 한다.
    """

    narrators: list[Narrator]
    attempt_timeout: float
    budget: float = NARRATION_BUDGET_SECONDS
    attempts: int = ATTEMPTS_PER_MODEL
    pause: Callable[[], float] = random_pause
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    clock: Callable[[], float] = time.monotonic

    def has_time(self, started: float) -> bool:
        """started 부터 지금까지 쓴 시간에 한 번 더 부르는 시간을 더해도 상한 안인가."""
        return self.clock() - started + self.attempt_timeout <= self.budget

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        """차례대로 부른다. 처음 받은 장면을 돌려준다. 끝내 못 받으면 NarrationFailed."""
        started = self.clock()
        reason = 'no_model'
        for narrator in self.narrators:
            for number in range(self.attempts):
                if number > 0:
                    await self.sleep(self.pause())
                if not self.has_time(started):
                    raise NarrationFailed(reason)
                try:
                    return await narrator.narrate(request, preview)
                except (ProviderError, NarrationError) as error:
                    reason = str(error)
                if not can_retry(reason):
                    break
            if not can_fall_back(reason):
                break
        raise NarrationFailed(reason)
