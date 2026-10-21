# asset-server/app/observability/metrics.py

"""
메트릭의 계측기와, 그것을 OTLP(HTTP)로 수집기(Alloy)에 미는 것.
이름과 label 은 docs/observability.md 의 "메트릭"에 있다.
결제 서버(internal/metrics)가 본보기다. 이 서버가 Python 의 본보기다.

계측기는 한 묶음(Instruments)으로 이 모듈에 둔다. 요청, DB, 작업을 세는 곳이 instruments() 로 꺼내 쓴다.
MeterProvider 는 OpenTelemetry 의 전역에 두지 않는다. 전역은 프로세스에 한 번만 바꿀 수 있어
테스트가 바꿔 끼우지 못한다.
서버가 뜰 때(configure_metrics)와 테스트가 use_meter_provider 로 바꿔 끼우면 계측기를 그것으로 다시 만든다.
처음에는 아무것도 하지 않는 것(NoOp)이다. 보낼 곳이 없으면 계측은 그대로 돌고 보내기만 없다.

모은 값은 15초(OTEL_METRIC_EXPORT_INTERVAL)마다 따로 도는 스레드가 보낸다. 요청은 보내기를 기다리지 않는다.
수집기가 죽어 있어도 서버는 뜨고 요청은 영향을 받지 않는다. 보내지 못한 묶음은 버린다.
"""

import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import (
    CallbackOptions,
    Counter,
    Histogram,
    Meter,
    MeterProvider,
    NoOpMeterProvider,
    Observation,
    UpDownCounter,
    _Gauge,  # 동기 gauge 의 타입. API 가 이 이름으로 내보낸다
)
from opentelemetry.sdk.metrics import MeterProvider as SdkMeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from app.core.config import Settings
from app.observability.setup import SERVICE_NAME

# OTLP(HTTP)로 메트릭을 받는 주소의 끝. 보내는 주소 뒤에 붙인다
METRICS_PATH = '/v1/metrics'
# 수집기의 답을 기다리는 가장 긴 시간(초). 끌 때 남은 것을 보내는 것도 이만큼에서 포기한다
EXPORT_TIMEOUT_SECONDS = 5
# 시간을 재는 히스토그램의 구간(초). SDK 의 기본 구간은 밀리초를 가정한 숫자라 초로 재면 거의 모두 첫 칸에 든다.
# 다섯 서버가 같은 구간을 쓴다(docs/observability.md 의 "계측기를 만드는 법")
DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
# 메서드 label 로 받는 것. 그 밖은 _OTHER 다. 받은 글자를 그대로 label 로 쓰면 시계열이 끝없이 는다
KNOWN_METHODS = frozenset({'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'CONNECT', 'TRACE'})
OTHER_METHOD = '_OTHER'
# 작업이 끝난 모양. 로그의 result 와 같다
JOB_SUCCESS = 'success'
JOB_FAILED = 'server_error'
JOB_CANCELLED = 'cancelled'


@dataclass(frozen=True)
class PoolStats:
    """연결 풀의 지금 값을 읽는 것. 쉬는 연결, 쓰는 연결, 가질 수 있는 가장 많은 연결."""

    idle: Callable[[], int]
    in_use: Callable[[], int]
    maximum: int


@dataclass(frozen=True)
class Instruments:
    """이 서버의 계측기 묶음. 이름에서 _total 과 단위를 뗀 것이다. Alloy 가 붙여 표의 이름이 된다."""

    http_requests: Counter
    http_request_duration: Histogram
    http_active_requests: UpDownCounter
    db_up: _Gauge
    db_pool_wait: Histogram
    jobs_started: Counter
    jobs_finished: Counter
    jobs_running: UpDownCounter
    job_duration: Histogram


# 지금 지켜보는 연결 풀. 앱이 뜰 때 하나를 건다(watch_pool). 앱에 하나다
_watched_pool: PoolStats | None = None


def watch_pool(stats: PoolStats) -> None:
    """연결 풀의 값을 메트릭으로 내보내기 시작한다. 앞에 건 것을 바꾼다."""
    global _watched_pool
    _watched_pool = stats


def observe_pool_connections(options: CallbackOptions) -> Iterable[Observation]:
    """db_pool_connections 의 값. 수집할 때마다 SDK 가 부른다. 지켜보는 풀이 없으면 아무것도 없다."""
    pool = _watched_pool
    if pool is None:
        return []
    return [Observation(pool.idle(), {'state': 'idle'}), Observation(pool.in_use(), {'state': 'in_use'})]


def observe_pool_maximum(options: CallbackOptions) -> Iterable[Observation]:
    """db_pool_connections_max 의 값."""
    pool = _watched_pool
    return [] if pool is None else [Observation(pool.maximum)]


def duration_histogram(meter: Meter, name: str, description: str) -> Histogram:
    """초로 재는 히스토그램. 구간은 DURATION_BUCKETS 다."""
    return meter.create_histogram(
        name, unit='s', description=description, explicit_bucket_boundaries_advisory=DURATION_BUCKETS
    )


def build_instruments(meter: Meter) -> Instruments:
    """meter 로 계측기를 만든다. 연결 풀의 값은 수집할 때 읽는 gauge 로 건다."""
    meter.create_observable_gauge(
        'db_pool_connections', callbacks=[observe_pool_connections], description='연결 풀의 연결 수'
    )
    meter.create_observable_gauge(
        'db_pool_connections_max', callbacks=[observe_pool_maximum], description='풀이 가질 수 있는 가장 많은 연결'
    )
    return Instruments(
        http_requests=meter.create_counter('http_server_requests', description='끝난 요청의 수'),
        http_request_duration=duration_histogram(
            meter, 'http_server_request_duration', '요청을 받아 응답을 끝낼 때까지'
        ),
        http_active_requests=meter.create_up_down_counter(
            'http_server_active_requests', description='지금 처리 중인 요청의 수'
        ),
        db_up=meter.create_gauge('db_up', description='준비 상태 확인이 마지막으로 본 DB 의 상태. 1 이면 닿는다'),
        db_pool_wait=duration_histogram(meter, 'db_pool_wait', '연결을 얻으려고 기다린 시간'),
        jobs_started=meter.create_counter('background_jobs_started', description='시작한 작업의 수'),
        jobs_finished=meter.create_counter('background_jobs_finished', description='끝난 작업의 수'),
        jobs_running=meter.create_up_down_counter('background_jobs_running', description='지금 도는 작업의 수'),
        job_duration=duration_histogram(meter, 'background_job_duration', '작업 하나가 걸린 시간'),
    )


_provider: MeterProvider = NoOpMeterProvider()
_instruments: Instruments = build_instruments(_provider.get_meter(SERVICE_NAME))


def use_meter_provider(provider: MeterProvider) -> None:
    """메트릭을 모으는 것을 바꿔 끼우고 계측기를 그것으로 다시 만든다. 서버가 뜰 때와 테스트가 부른다."""
    global _provider, _instruments
    _provider = provider
    _instruments = build_instruments(provider.get_meter(SERVICE_NAME))


def instruments() -> Instruments:
    """지금 끼운 것의 계측기."""
    return _instruments


def method_label(method: str) -> str:
    """메서드 label. 정한 것이 아니면 _OTHER 다."""
    return method if method in KNOWN_METHODS else OTHER_METHOD


def record_request(method: str, route: str, status_code: int, seconds: float) -> None:
    """끝난 요청 하나를 센다. route 는 경로의 틀이다(실제 주소가 아니다)."""
    labels = {'method': method_label(method), 'route': route}
    _instruments.http_requests.add(1, {**labels, 'status_code': status_code})
    _instruments.http_request_duration.record(seconds, labels)


def record_db_up(reachable: bool) -> None:
    """준비 상태 확인이 본 DB 의 상태를 적는다."""
    _instruments.db_up.set(1 if reachable else 0)


def record_pool_wait(seconds: float) -> None:
    """연결 하나를 얻으려고 기다린 시간을 적는다."""
    _instruments.db_pool_wait.record(seconds)


@contextmanager
def measured_job(operation: str) -> Iterator[None]:
    """
    작업 하나(정리 작업의 한 바퀴)를 센다. 시작, 도는 수, 걸린 시간, 끝난 모양(result)이다.

    예외는 그대로 올린다. 끄느라 멈춘 것(CancelledError)은 실패가 아니라 cancelled 다.
    """
    labels = {'operation': operation}
    measured = _instruments
    measured.jobs_started.add(1, labels)
    measured.jobs_running.add(1, labels)
    started = time.perf_counter()
    result = JOB_SUCCESS
    try:
        yield
    except Exception:
        result = JOB_FAILED
        raise
    except BaseException:
        result = JOB_CANCELLED
        raise
    finally:
        measured.jobs_running.add(-1, labels)
        measured.job_duration.record(time.perf_counter() - started, labels)
        measured.jobs_finished.add(1, {**labels, 'result': result})


def build_meter_provider(settings: Settings, resource: Resource) -> SdkMeterProvider | None:
    """메트릭을 보내는 MeterProvider 를 만든다. 보낼 곳이 없으면 None 이다. 만드는 것만으로는 수집기에 닿지 않는다."""
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        return None
    exporter = OTLPMetricExporter(endpoint=endpoint + METRICS_PATH, timeout=EXPORT_TIMEOUT_SECONDS)
    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=settings.otel_metric_export_interval,
        export_timeout_millis=EXPORT_TIMEOUT_SECONDS * 1000,
    )
    return SdkMeterProvider(resource=resource, metric_readers=[reader])


def configure_metrics(settings: Settings, resource: Resource) -> SdkMeterProvider | None:
    """
    보낼 곳이 있으면 메트릭을 보내는 것을 만들어 끼운다. 만든 것을 돌려준다. 없으면 None 이다.

    보낼 곳이 없으면 끼워 둔 것을 건드리지 않는다. 테스트가 끼운 것(메모리에 모으는 것)이 그대로 남는다.
    """
    provider = build_meter_provider(settings, resource)
    if provider is not None:
        use_meter_provider(provider)
    return provider


def shutdown_metrics(provider: SdkMeterProvider | None) -> None:
    """
    모아 둔 값을 한 번 보내고 끈다. 서버가 꺼질 때 부른다. 보내기를 기다리느라 막히므로 스레드에서 부른다(app/main.py).

    수집기가 답하지 않으면 EXPORT_TIMEOUT_SECONDS 뒤에 버리고 끈다.
    """
    if provider is not None:
        provider.shutdown(timeout_millis=EXPORT_TIMEOUT_SECONDS * 1000)
