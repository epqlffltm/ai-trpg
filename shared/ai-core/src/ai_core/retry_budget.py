# shared/ai-core/src/ai_core/retry_budget.py

"""
같은 모델로 다시 부르는 것(재시도)의 예산. 공급자가 아플 때 재시도가 일을 몇 배로 키우지 않게 한다.

서술 하나는 같은 모델로 두 번까지 부르고(app/rounds/retrying_narrator.py), 방장은 실패한 라운드를 두 번까지 다시 맡긴다.
층마다 다시 하면 일이 곱해진다. 공급자가 내려가 모든 테이블의 서술이 실패하는 동안 모두가 두 번씩 부르면
우리 원가도, 공급자의 부하도 두 배가 된다. 그래서 맨 안쪽(같은 모델로 다시 부르기)에 비율의 상한을 둔다.

규칙은 Google SRE 의 과부하 지침과 Finagle 의 RetryBudget 을 따른다.
  - 최근 WINDOW_SECONDS 동안 그 모델에 보낸 첫 시도 수의 RATIO 만큼만 다시 부를 수 있다.
  - 손님이 적을 때 한 번의 실패로 예산이 막히지 않게, 비율과 상관없이 FLOOR 번은 늘 다시 부를 수 있다.
  - 예산이 없으면 다시 부르지 않고 그 시도의 실패로 끝낸다. 라운드는 실패로 적히고 방장이 다시 맡길 수 있다.
모델(설정에 적은 이름)마다 따로 센다. 한 모델이 아파도 다른 모델의 재시도를 막지 않는다.

서버(프로세스)마다 따로 센다. 서버가 여럿이면 예산도 그만큼이다. 공급자를 지키는 데에는 그것으로 충분하다.
DB 나 Redis 에 두지 않는다. 재시도를 정할 때마다 바깥을 부르면 그것이 또 실패할 수 있다.
"""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

# 최근 몇 초의 시도를 세는가
WINDOW_SECONDS = 60.0
# 첫 시도 수에 대한 재시도의 비율. Google SRE 지침의 값이다
RATIO = 0.1
# 비율과 상관없이 늘 허락하는 재시도 수(WINDOW_SECONDS 마다)
FLOOR = 3


def forget_before(times: deque[float], since: float) -> None:
    """since 보다 오래된 시각을 앞에서부터 버린다. times 는 오래된 것부터 들어 있다."""
    while times and times[0] < since:
        times.popleft()


def allowance(requests: int, ratio: float, floor: int) -> int:
    """첫 시도가 requests 번일 때 허락하는 재시도 수."""
    return max(floor, int(requests * ratio))


@dataclass
class RetryBudget:
    """
    모델마다의 재시도 예산. 앱에 하나만 두고 모든 서술자가 함께 쓴다(app/rounds/narrator_setup.py).

    clock 은 테스트가 바꿔 꽂는다. 비동기 코드에서만 부르고 기다리는 일이 없어 잠금이 필요 없다.
    """

    window: float = WINDOW_SECONDS
    ratio: float = RATIO
    floor: int = FLOOR
    clock: Callable[[], float] = time.monotonic
    requests: dict[str, deque[float]] = field(default_factory=dict)
    retries: dict[str, deque[float]] = field(default_factory=dict)

    def recent(self, book: dict[str, deque[float]], key: str) -> deque[float]:
        """그 모델의 최근 시각들. 창 밖의 것은 버린 뒤다."""
        times = book.setdefault(key, deque())
        forget_before(times, self.clock() - self.window)
        return times

    def note_request(self, key: str) -> None:
        """그 모델에 첫 시도를 보낸다고 적는다."""
        self.recent(self.requests, key).append(self.clock())

    def try_retry(self, key: str) -> bool:
        """그 모델로 다시 불러도 되는가. 되면 재시도를 적고 True, 예산이 없으면 False."""
        retries = self.recent(self.retries, key)
        if len(retries) >= allowance(len(self.recent(self.requests, key)), self.ratio, self.floor):
            return False
        retries.append(self.clock())
        return True
