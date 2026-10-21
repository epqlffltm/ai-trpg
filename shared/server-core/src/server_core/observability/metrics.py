# shared/server-core/src/server_core/observability/metrics.py

"""
메트릭의 계측기와, 그것을 OTLP(HTTP)로 수집기(Alloy)에 미는 것.
이름과 label 은 저장소 루트의 docs/observability.md 의 "메트릭"에 있다. 결제 서버(internal/metrics)가 본보기다.

여기에는 FastAPI 서버들이 모두 세는 것만 둔다. 요청, DB, 뒤의 작업, SSE 연결이다.
서버만의 것(알림 서버의 받은 알림, 게임 서버의 서술)은 서버가 계측기 묶음(InstrumentSet)으로 더한다.

    def build(meter: Meter) -> NotificationInstruments:
        return NotificationInstruments(received=meter.create_counter('notifications_received', ...))

    _instruments = InstrumentSet(build)
    _instruments.get().received.add(1, {...})

MeterProvider 는 OpenTelemetry 의 전역에 두지 않는다. 전역은 프로세스에 한 번만 바꿀 수 있어
테스트가 바꿔 끼우지 못한다.
서버가 뜰 때(configure_metrics)와 테스트가 use_meter_provider 로 바꿔 끼우면 묶음 모두를 그것으로 다시 만든다.
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

from server_core.settings import CoreSettings

# OTLP(HTTP)로 메트릭을 받는 주소의 끝. 보내는 주소 뒤에 붙인다
METRICS_PATH = '/v1/metrics'
# 수집기의 답을 기다리는 가장 긴 시간(초). 끌 때 남은 것을 보내는 것도 이만큼에서 포기한다
EXPORT_TIMEOUT_SECONDS = 5
# 계측기를 만드는 쪽의 이름(instrumentation scope). 서버가 끼울 때 서비스 이름을 준다. Alloy 는 label 로 붙이지 않는다
DEFAULT_SCOPE_NAME = 'server'
# 시간을 재는 히스토그램의 구간(초). SDK 의 기본 구간은 밀리초를 가정한 숫자라 초로 재면 거의 모두 첫 칸에 든다.
# 다섯 서버가 같은 구간을 쓴다(docs/observability.md 의 "계측기를 만드는 법")
DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
# AI 호출과 서술처럼 긴 것의 구간. 같은 구간에 30, 60, 120 초를 더한다
LONG_DURATION_BUCKETS = (*DURATION_BUCKETS, 30, 60, 120)
# SSE 연결이 이어진 시간의 구간(초). 연결은 몇 초에서 몇 시간이다. 1초, 10초, 1분, 5분, 15분, 30분, 1·2·4시간
STREAM_BUCKETS = (1, 10, 60, 300, 900, 1800, 3600, 7200, 14400)
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
    """모든 서버의 계측기 묶음. 이름에서 _total 과 단위를 뗀 것이다. Alloy 가 붙여 표의 이름이 된다."""

    http_requests: Counter
    http_request_duration: Histogram
    http_active_requests: UpDownCounter
    db_up: _Gauge
    db_pool_wait: Histogram
    jobs_started: Counter
    jobs_finished: Counter
    jobs_running: UpDownCounter
    job_duration: Histogram
    sse_connections: UpDownCounter
    sse_connections_opened: Counter
    sse_connection_duration: Histogram


class InstrumentSet[T]:
    """
    계측기 한 묶음. 만드는 함수(build)를 받아 두었다가, 메트릭을 모으는 것이 바뀌면 그것으로 다시 만든다.

    서버가 제 계측기를 더하는 자리다. 모듈을 불러올 때 하나 만들어 두고 get() 으로 꺼내 쓴다.
    만든 묶음은 이 모듈이 기억한다(_sets). 바꿔 끼울 때(use_meter_provider) 모두 다시 만든다.
    """

    def __init__(self, build: Callable[[Meter], T]) -> None:
        self._build = build
        self._current = build(_meter())
        _sets.append(self)

    def rebuild(self, meter: Meter) -> None:
        """새 meter 로 다시 만든다."""
        self._current = self._build(meter)

    def get(self) -> T:
        """지금 끼운 것의 계측기."""
        return self._current


# 지금 지켜보는 연결 풀. 앱이 뜰 때 하나를 건다(watch_pool). 앱에 하나다
_watched_pool: PoolStats | None = None
_provider: MeterProvider = NoOpMeterProvider()
_scope_name: str = DEFAULT_SCOPE_NAME
# 만든 계측기 묶음들. 바꿔 끼울 때 모두 다시 만든다
_sets: list[InstrumentSet] = []


def _meter() -> Meter:
    """지금 끼운 것의 meter."""
    return _provider.get_meter(_scope_name)


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


def duration_histogram(
    meter: Meter, name: str, description: str, buckets: tuple[float, ...] = DURATION_BUCKETS
) -> Histogram:
    """초로 재는 히스토그램. 구간은 주지 않으면 DURATION_BUCKETS 다. 서버가 제 계측기를 만들 때도 쓴다."""
    return meter.create_histogram(name, unit='s', description=description, explicit_bucket_boundaries_advisory=buckets)


def build_instruments(meter: Meter) -> Instruments:
    """meter 로 모든 서버의 계측기를 만든다. 연결 풀의 값은 수집할 때 읽는 gauge 로 건다."""
    meter.create_observable_gauge(
        'db_pool_connections', callbacks=[observe_pool_connections], description='연결 풀의 연결 수'
    )
    meter.create_observable_gauge(
        'db_pool_connections_max', callbacks=[observe_pool_maximum], description='풀이 가질 수 있는 가장 많은 연결'
    )
    return Instruments(
        http_requests=meter.create_counter('http_server_requests', description='끝난 요청의 수'),
        http_request_duration=duration_histogram(
            meter, 'http_server_request_duration', '요청을 받아 응답을 끝낼 때까지. SSE 스트림은 뺀다'
        ),
        http_active_requests=meter.create_up_down_counter(
            'http_server_active_requests', description='지금 처리 중인 요청의 수. SSE 스트림은 뺀다'
        ),
        db_up=meter.create_gauge('db_up', description='준비 상태 확인이 마지막으로 본 DB 의 상태. 1 이면 닿는다'),
        db_pool_wait=duration_histogram(meter, 'db_pool_wait', '연결을 얻으려고 기다린 시간'),
        jobs_started=meter.create_counter('background_jobs_started', description='시작한 작업의 수'),
        jobs_finished=meter.create_counter('background_jobs_finished', description='끝난 작업의 수'),
        jobs_running=meter.create_up_down_counter('background_jobs_running', description='지금 도는 작업의 수'),
        job_duration=duration_histogram(meter, 'background_job_duration', '작업 하나가 걸린 시간'),
        sse_connections=meter.create_up_down_counter('sse_connections', description='지금 열려 있는 SSE 연결의 수'),
        sse_connections_opened=meter.create_counter('sse_connections_opened', description='열린 SSE 연결의 수'),
        sse_connection_duration=duration_histogram(
            meter, 'sse_connection_duration', 'SSE 연결이 이어진 시간', STREAM_BUCKETS
        ),
    )


_instruments: InstrumentSet[Instruments] = InstrumentSet(build_instruments)


def use_meter_provider(provider: MeterProvider, scope_name: str = DEFAULT_SCOPE_NAME) -> None:
    """
    메트릭을 모으는 것을 바꿔 끼우고 계측기 묶음을 모두 그것으로 다시 만든다. 서버가 뜰 때와 테스트가 부른다.

    scope_name 은 계측기를 만드는 쪽의 이름이다. 서버가 뜰 때는 서비스 이름이다(configure_metrics).
    """
    global _provider, _scope_name
    _provider = provider
    _scope_name = scope_name
    meter = _meter()
    for instrument_set in _sets:
        instrument_set.rebuild(meter)


def instruments() -> Instruments:
    """지금 끼운 것의 모든 서버의 계측기."""
    return _instruments.get()


# --- HTTP 와 DB ---


def method_label(method: str) -> str:
    """메서드 label. 정한 것이 아니면 _OTHER 다."""
    return method if method in KNOWN_METHODS else OTHER_METHOD


def record_request(method: str, route: str, status_code: int, seconds: float | None) -> None:
    """
    끝난 요청 하나를 센다. route 는 경로의 틀이다(실제 주소가 아니다).

    seconds 가 None 이면 걸린 시간을 적지 않는다. SSE 스트림이다(request_metrics.py).
    """
    measured = instruments()
    labels = {'method': method_label(method), 'route': route}
    measured.http_requests.add(1, {**labels, 'status_code': status_code})
    if seconds is not None:
        measured.http_request_duration.record(seconds, labels)


def record_db_up(reachable: bool) -> None:
    """준비 상태 확인이 본 DB 의 상태를 적는다."""
    instruments().db_up.set(1 if reachable else 0)


def record_pool_wait(seconds: float) -> None:
    """연결 하나를 얻으려고 기다린 시간을 적는다."""
    instruments().db_pool_wait.record(seconds)


# --- 작업과 스트림 ---


@contextmanager
def measured_job(operation: str) -> Iterator[None]:
    """
    작업 하나(맡긴 작업 하나, 도는 작업의 한 바퀴)를 센다. 시작, 도는 수, 걸린 시간, 끝난 모양(result)이다.

    예외는 그대로 올린다. 끄느라 멈춘 것(CancelledError)은 실패가 아니라 cancelled 다.
    """
    labels = {'operation': operation}
    measured = instruments()
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


@contextmanager
def measured_stream() -> Iterator[None]:
    """SSE 연결 하나를 센다. 열린 수, 지금 열린 수, 이어진 시간이다. 어떻게 끝났든(끊김, 취소) 센다."""
    measured = instruments()
    measured.sse_connections_opened.add(1)
    measured.sse_connections.add(1)
    started = time.perf_counter()
    try:
        yield
    finally:
        measured.sse_connections.add(-1)
        measured.sse_connection_duration.record(time.perf_counter() - started)


# --- 보내기 ---


def build_meter_provider(settings: CoreSettings, resource: Resource) -> SdkMeterProvider | None:
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


def configure_metrics(settings: CoreSettings, resource: Resource) -> SdkMeterProvider | None:
    """
    보낼 곳이 있으면 메트릭을 보내는 것을 만들어 끼운다. 만든 것을 돌려준다. 없으면 None 이다.

    보낼 곳이 없으면 끼워 둔 것을 건드리지 않는다. 테스트가 끼운 것(메모리에 모으는 것)이 그대로 남는다.
    """
    provider = build_meter_provider(settings, resource)
    if provider is not None:
        use_meter_provider(provider, settings.service_name)
    return provider


def shutdown_metrics(provider: SdkMeterProvider | None) -> None:
    """
    모아 둔 값을 한 번 보내고 끈다. 서버가 꺼질 때 부른다.
    보내기를 기다리느라 막히므로 스레드에서 부른다(서버의 app/main.py).

    수집기가 답하지 않으면 EXPORT_TIMEOUT_SECONDS 뒤에 버리고 끈다.
    """
    if provider is not None:
        provider.shutdown(timeout_millis=EXPORT_TIMEOUT_SECONDS * 1000)
