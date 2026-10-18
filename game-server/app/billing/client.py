# game-server/app/billing/client.py

"""
결제 서버를 부르는 것의 모양과 그 결과.

구현은 둘이다. 실제로 부르는 것(http_billing.py)과 받지 않는 것(free_billing.py). 설정(BILLING_URL)이 고른다(setup.py).
서술자(Narrator)처럼 모양만 여기 두고 구현을 갈아 끼운다. 테스트는 가짜 결제 서버로 가는 실제 구현을 쓴다.

네 일(걸기, 확정, 반환, 연장) 모두 이름표(reference)로 홀드를 가리킨다.
결제 서버는 같은 이름표면 같은 일로 보고 한 번만 한다.
그래서 응답을 받지 못했으면 같은 것을 그대로 다시 부르면 된다.

실패는 둘로 나눈다. 다시 부르면 될 수 있는 것(BillingUnavailable)과 다시 불러도 같은 것(BillingRejected).
앞의 것은 정리 작업이 조금 뒤에 다시 부르고, 뒤의 것은 사람이 봐야 하는 일이라 오류로 남긴다.
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class HoldResult(enum.StrEnum):
    """홀드를 걸어 본 결과."""

    # 크레딧을 빼 두었다. 이미 걸어 둔 것을 돌려받은 것도 여기다
    HELD = 'held'
    # 크레딧이 모자란다. 하나도 빼지 않았고 홀드도 남지 않았다. 충전한 뒤 같은 이름표로 다시 걸 수 있다
    SHORT = 'short'
    # 프리미엄 가격표라 골드(유료 크레딧)로만 내는데 골드가 모자란다(credit.gold_required). 실버가 얼마나 있든 같다.
    # 모자람과 같이 홀드가 남지 않는다. 골드를 산 뒤 같은 이름표로 다시 걸 수 있다
    GOLD_REQUIRED = 'gold_required'


class ExtendResult(enum.StrEnum):
    """홀드를 연장해 본 결과. 결제 서버의 홀드는 걸거나 연장한 때부터 HOLD_TTL(기본 24시간) 뒤에 만료된다."""

    # 만료 시각을 지금부터 HOLD_TTL 뒤로 밀었다
    EXTENDED = 'extended'
    # 그 이름표의 홀드가 없다. 같은 이름표로 다시 걸 수 있다
    MISSING = 'missing'
    # 이미 끝난 홀드다. 만료되어 결제 서버가 돌려준 것이다. 같은 이름표로는 다시 걸 수 없다
    ENDED = 'ended'


@dataclass(frozen=True)
class HoldOutcome:
    """홀드를 걸어 본 결과와, 잡혔으면 결제 서버가 정한 만료 시각(UTC). 결제 서버가 시각을 주지 않으면 None."""

    result: HoldResult
    expires_at: datetime | None = None


@dataclass(frozen=True)
class ExtendOutcome:
    """홀드를 연장해 본 결과와, 연장했으면 새 만료 시각(UTC). 결제 서버가 시각을 주지 않으면 None."""

    result: ExtendResult
    expires_at: datetime | None = None


class BillingUnavailable(Exception):
    """
    결제 서버의 답을 받지 못했거나, 지금은 처리할 수 없다고 했다. 조금 뒤에 다시 부르면 될 수 있다.

    reason 은 짧은 이름이다(unreachable, timeout, server_error, unauthorized, bad_response).
    응답의 본문은 싣지 않는다. 무엇이 들어 있을지 모른다.
    unauthorized 는 서명이 거절된 것이다. 두 서버의 비밀이 다르거나 시계가 어긋났다. 설정을 고치면 낫는다.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# 결제 서버가 가격표의 이름을 받지 않을 때의 오류의 이름. 판매를 멈췄거나, 그런 이름이 없거나 아직 열지 않았다
PRICE_UNAVAILABLE = frozenset({'price.not_for_sale', 'price.unknown'})
# 결제 서버가 골드가 모자란다고 할 때의 오류의 이름(402)
GOLD_REQUIRED_CODE = 'credit.gold_required'


class BillingRejected(Exception):
    """
    결제 서버가 요청을 받아들이지 않았다. 다시 불러도 같다. 이름표를 짓는 코드의 버그이거나 두 서버의 기록이 어긋났다.

    status_code 는 결제 서버의 답이다(400, 404, 409 …). 본문은 싣지 않는다.

    code 는 결제 서버가 붙인 오류의 이름이다(price.not_for_sale, price.unknown …). 없으면 None.
    가격표의 이름을 팔지 않는 것(PRICE_UNAVAILABLE)은 버그가 아니다. 판매를 멈췄거나 아직 열지 않은 모델이다.
    """

    def __init__(self, status_code: int, code: str | None = None) -> None:
        super().__init__(f'billing rejected: {status_code}')
        self.status_code = status_code
        self.code = code

    @property
    def price_unavailable(self) -> bool:
        """그 가격표의 이름을 지금 팔지 않아서 거절했나."""
        return self.code in PRICE_UNAVAILABLE


class Billing(Protocol):
    """결제 서버를 부르는 것."""

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldOutcome:
        """user_id 의 크레딧을 가격표 price_code 의 값만큼 빼 둔다. 모자라면 SHORT."""
        ...

    async def capture(self, reference: str) -> None:
        """홀드를 확정한다. 크레딧은 돌아가지 않는다. 이미 확정했으면 아무것도 하지 않는다."""
        ...

    async def release(self, reference: str) -> None:
        """홀드를 돌려준다. 이미 돌려줬거나 걸린 적이 없으면 아무것도 하지 않는다."""
        ...

    async def extend(self, reference: str) -> ExtendOutcome:
        """홀드의 만료 시각을 지금부터 HOLD_TTL 뒤로 민다. 크레딧은 건드리지 않는다."""
        ...
