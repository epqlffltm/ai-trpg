# chat-server/app/billing/metered.py

"""
결제 서버를 부를 때마다 세는 것(billing_calls_total). 결제 서버를 부르는 것(Billing)을 감싼다.
게임 서버의 것(trpg-server/app/billing/metered.py)과 같다. 계측기는 app/billing/metrics.py 다.

부르는 것(http_billing.py)은 그대로 두고 밖에서 센다. 결제 서버의 결제 대행사 메트릭(payment.Measured)과 같은 모양이다.
결제 서버를 쓸 때만 감싼다(setup.py). 받지 않는 것(FreeBilling)은 부르지 않으니 셀 것이 없다.

outcome 은 결과의 이름이다.
  - 걸기: held, short, gold_required
  - 확정, 반환: done
  - 연장: done, missing(홀드가 없다), ended(이미 끝났다)
  - 넷 모두: unavailable(답을 받지 못했다. 다시 부른다), rejected(받아들이지 않았다. 사람이 볼 일이다)
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.billing.client import Billing, BillingRejected, BillingUnavailable, ExtendOutcome, ExtendResult, HoldOutcome
from app.billing.metrics import record_billing_call

HOLD = 'hold'
CAPTURE = 'capture'
RELEASE = 'release'
EXTEND = 'extend'
DONE = 'done'
UNAVAILABLE = 'unavailable'
REJECTED = 'rejected'


async def measured[Result](operation: str, call: Awaitable[Result], outcome_of: Callable[[Result], str]) -> Result:
    """부르기 하나를 기다리고 그 결과를 센다. 예외는 센 뒤에 그대로 올린다."""
    try:
        result = await call
    except BillingUnavailable:
        record_billing_call(operation, UNAVAILABLE)
        raise
    except BillingRejected:
        record_billing_call(operation, REJECTED)
        raise
    record_billing_call(operation, outcome_of(result))
    return result


def hold_outcome(outcome: HoldOutcome) -> str:
    """걸어 본 결과의 이름."""
    return outcome.result.value


def extend_outcome(outcome: ExtendOutcome) -> str:
    """연장해 본 결과의 이름. 연장했으면 done 이다."""
    return DONE if outcome.result == ExtendResult.EXTENDED else outcome.result.value


def done(_: None) -> str:
    """돌려주는 것이 없는 일(확정, 반환)이 끝났다."""
    return DONE


@dataclass(frozen=True)
class MeteredBilling:
    """결제 서버를 부르고 센다. 부르는 것은 inner 가 한다."""

    inner: Billing

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldOutcome:
        return await measured(HOLD, self.inner.hold(reference, user_id, price_code), hold_outcome)

    async def capture(self, reference: str) -> None:
        await measured(CAPTURE, self.inner.capture(reference), done)

    async def release(self, reference: str) -> None:
        await measured(RELEASE, self.inner.release(reference), done)

    async def extend(self, reference: str) -> ExtendOutcome:
        return await measured(EXTEND, self.inner.extend(reference), extend_outcome)
