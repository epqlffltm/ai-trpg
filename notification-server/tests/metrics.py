# notification-server/tests/metrics.py

"""
테스트가 센 메트릭을 읽는 도구.
메모리에 모으는 것(InMemoryMetricReader)을 끼우고(metrics.use_meter_provider),
끝나면 아무것도 하지 않는 것으로 되돌린다.

보내는 일(OTLP)은 하지 않는다. 보내는 길은 test_metrics_setup.py 가 본다.
이름은 계측기의 이름이다(http_server_requests). Prometheus 의 이름(_total, _seconds)은 Alloy 가 붙인다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from opentelemetry.metrics import NoOpMeterProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import HistogramDataPoint, InMemoryMetricReader

from app.observability.metrics import use_meter_provider


@dataclass(frozen=True)
class Point:
    """메트릭의 점 하나. label 과 값(셈은 그 수, 히스토그램은 잰 횟수와 합)."""

    labels: dict
    value: float
    unit: str


class MetricsRecorder:
    """테스트 하나가 센 메트릭을 모은다."""

    def __init__(self) -> None:
        self.reader = InMemoryMetricReader()
        self.provider = MeterProvider(metric_readers=[self.reader])

    def points(self, name: str) -> list[Point]:
        """그 이름의 점들. 히스토그램은 잰 횟수가 값이다."""
        data = self.reader.get_metrics_data()
        if data is None:
            return []
        return [
            Point(dict(point.attributes or {}), point_value(point), metric.unit)
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == name
            for point in metric.data.data_points
        ]

    def value(self, name: str, **labels: object) -> float | None:
        """label 이 모두 맞는 점의 값. 없으면 None 이다."""
        found = [point.value for point in self.points(name) if all(point.labels.get(k) == v for k, v in labels.items())]
        assert len(found) <= 1, f'{name}{labels} 에 맞는 점이 {len(found)} 개다'
        return found[0] if found else None


def point_value(point: object) -> float:
    """점의 값. 히스토그램은 잰 횟수다."""
    if isinstance(point, HistogramDataPoint):
        return point.count
    return point.value


@contextmanager
def recording() -> Iterator[MetricsRecorder]:
    """메모리에 모으는 것을 끼우고, 끝나면 아무것도 하지 않는 것으로 되돌린다."""
    recorder = MetricsRecorder()
    use_meter_provider(recorder.provider)
    try:
        yield recorder
    finally:
        use_meter_provider(NoOpMeterProvider())
        recorder.provider.shutdown()
