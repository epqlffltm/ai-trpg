# story-server/tests/test_billing_metrics.py

"""
결제 서버를 부를 때마다 세는 것(app/billing/metered.py, metrics.py)을 검증한다. 게임 서버의 같은 테스트를 옮겼다.

결제 서버는 정해 둔 결과를 돌려주는 가짜다. 메트릭은 메모리에 모은다(metrics fixture).
"""

import uuid
from dataclasses import dataclass

import pytest
from server_core.testing.metrics import MetricsRecorder

from app.billing.client import (
    BillingRejected,
    BillingUnavailable,
    ExtendOutcome,
    ExtendResult,
    HoldOutcome,
    HoldResult,
)
from app.billing.metered import MeteredBilling

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')


@dataclass
class Answering:
    """정해 둔 결과를 돌려주거나 정해 둔 예외를 올리는 결제 서버."""

    held: HoldOutcome = HoldOutcome(HoldResult.HELD)
    extended: ExtendOutcome = ExtendOutcome(ExtendResult.EXTENDED)
    error: Exception | None = None

    def answer[Result](self, result: Result) -> Result:
        if self.error is not None:
            raise self.error
        return result

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldOutcome:
        return self.answer(self.held)

    async def capture(self, reference: str) -> None:
        return self.answer(None)

    async def release(self, reference: str) -> None:
        return self.answer(None)

    async def extend(self, reference: str) -> ExtendOutcome:
        return self.answer(self.extended)


async def call_all(billing: MeteredBilling) -> None:
    """네 일을 한 번씩 부른다."""
    await billing.hold('r', ME, 'p')
    await billing.capture('r')
    await billing.release('r')
    await billing.extend('r')


async def test_billing_calls_are_counted_by_operation_and_outcome(metrics: MetricsRecorder):
    await call_all(MeteredBilling(Answering()))
    await MeteredBilling(Answering(held=HoldOutcome(HoldResult.SHORT))).hold('r', ME, 'p')
    await MeteredBilling(Answering(held=HoldOutcome(HoldResult.GOLD_REQUIRED))).hold('r', ME, 'p')
    await MeteredBilling(Answering(extended=ExtendOutcome(ExtendResult.MISSING))).extend('r')
    await MeteredBilling(Answering(extended=ExtendOutcome(ExtendResult.ENDED))).extend('r')

    counted = {
        (point.labels['operation'], point.labels['outcome']): point.value for point in metrics.points('billing_calls')
    }
    assert counted == {
        ('hold', 'held'): 1,
        ('hold', 'short'): 1,
        ('hold', 'gold_required'): 1,
        ('capture', 'done'): 1,
        ('release', 'done'): 1,
        ('extend', 'done'): 1,
        ('extend', 'missing'): 1,
        ('extend', 'ended'): 1,
    }


@pytest.mark.parametrize(
    ('error', 'outcome'), [(BillingUnavailable('timeout'), 'unavailable'), (BillingRejected(409), 'rejected')]
)
async def test_a_failed_billing_call_is_counted_and_raised(error: Exception, outcome: str, metrics: MetricsRecorder):
    billing = MeteredBilling(Answering(error=error))

    with pytest.raises(type(error)):
        await billing.capture('r')

    assert metrics.value('billing_calls', operation='capture', outcome=outcome) == 1
