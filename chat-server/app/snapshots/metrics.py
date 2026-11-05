# chat-server/app/snapshots/metrics.py

"""
끝나지 않은 장면 그림의 청구의 수(snapshot_charges)의 계측기(#983).
게임 서버와 같은 이름과 label 이다(docs/observability.md 의 "메트릭"). 메트릭의 출처(service)가 chat-server 라서
다른 서버의 수와 섞이지 않는다. 공용 코드의 계측기 묶음(server_core.observability.metrics.InstrumentSet)으로 더한다.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from opentelemetry.metrics import Meter, _Gauge
from server_core.observability.metrics import InstrumentSet


@dataclass(frozen=True)
class SnapshotInstruments:
    """장면 그림의 계측기."""

    snapshot_charges: _Gauge


def build(meter: Meter) -> SnapshotInstruments:
    """meter 로 장면 그림의 계측기를 만든다."""
    return SnapshotInstruments(
        snapshot_charges=meter.create_gauge('snapshot_charges', description='끝나지 않은 장면 그림의 청구의 수')
    )


_instruments: InstrumentSet[SnapshotInstruments] = InstrumentSet(build)


def record_snapshot_charges(counts: Mapping[str, int]) -> None:
    """끝나지 않은 장면 그림의 청구의 수를 상태마다 적는다. 없는 상태는 0 으로 준다(부르는 쪽이 모든 상태를 넣는다)."""
    measured = _instruments.get()
    for status, count in counts.items():
        measured.snapshot_charges.set(count, {'status': status})
