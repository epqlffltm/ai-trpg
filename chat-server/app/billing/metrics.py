# chat-server/app/billing/metrics.py

"""
결제 서버를 부른 수(billing_calls_total)의 계측기.
게임 서버와 같은 이름과 label 이다(docs/observability.md 의 "메트릭").

공용 코드의 계측기 묶음(server_core.observability.metrics.InstrumentSet)으로 더한다. 서버마다의 것을 더하는 자리다.
메트릭의 출처(service)가 chat-server 라서 게임 서버의 수와 섞이지 않는다.
"""

from dataclasses import dataclass

from opentelemetry.metrics import Counter, Meter
from server_core.observability.metrics import InstrumentSet


@dataclass(frozen=True)
class BillingInstruments:
    """결제의 계측기."""

    billing_calls: Counter


def build(meter: Meter) -> BillingInstruments:
    """meter 로 결제의 계측기를 만든다."""
    return BillingInstruments(billing_calls=meter.create_counter('billing_calls', description='결제 서버를 부른 수'))


_instruments: InstrumentSet[BillingInstruments] = InstrumentSet(build)


def record_billing_call(operation: str, outcome: str) -> None:
    """결제 서버를 부른 것 하나를 센다. operation 은 hold, capture, release, extend 다."""
    _instruments.get().billing_calls.add(1, {'operation': operation, 'outcome': outcome})
