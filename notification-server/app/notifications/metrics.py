# notification-server/app/notifications/metrics.py

"""
알림 서버만의 메트릭. 다른 서버가 넣은 알림의 수다(docs/observability.md 의 "메트릭").

요청, DB, 작업의 메트릭은 공용 코드(server_core/observability/metrics.py)가 센다.
이 계측기는 공용 코드가 열어 둔 자리(InstrumentSet)에 더한다. 메트릭을 모으는 것을 바꿔 끼우면 함께 다시 만들어진다.

  - notifications_received_total{source, outcome}: 서명을 확인한 서버(game, billing, board)와 넣은 결과
"""

from dataclasses import dataclass

from opentelemetry.metrics import Counter, Meter
from server_core.observability.metrics import InstrumentSet


@dataclass(frozen=True)
class NotificationInstruments:
    """알림 서버만의 계측기."""

    received: Counter


def build_instruments(meter: Meter) -> NotificationInstruments:
    """meter 로 알림 서버의 계측기를 만든다."""
    return NotificationInstruments(
        received=meter.create_counter(
            'notifications_received', description='다른 서버가 넣은 알림의 수. outcome 은 넣은 결과다'
        ),
    )


_instruments = InstrumentSet(build_instruments)


def record_notification(source: str, outcome: str) -> None:
    """다른 서버가 넣은 알림 하나를 센다. source 는 서명을 확인한 서버의 이름이다(game, billing, board)."""
    _instruments.get().received.add(1, {'source': source, 'outcome': outcome})
