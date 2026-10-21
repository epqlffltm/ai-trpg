# shared/server-core/tests/test_streams_and_sets.py

"""
서버가 끼우는 자리를 검증한다.

  - 스트림인 주소(server_core/observability/streams.py): 요청의 span 을 걸지 않고, 끝난 요청의 수에만 든다
  - SSE 연결의 메트릭(metrics.py 의 measured_stream)
  - 서버가 더하는 계측기 묶음(metrics.py 의 InstrumentSet): 모으는 것을 바꿔 끼우면 다시 만들어진다
  - 작업의 span(spans.py 의 job_span): 걸린 span 이 있으면 그 아래에, 없으면 새 추적으로
"""

from dataclasses import dataclass

from opentelemetry.metrics import Counter, Meter

from server_core.observability.metrics import STREAM_BUCKETS, InstrumentSet, measured_stream
from server_core.observability.request_metrics import RequestMetricsMiddleware
from server_core.observability.request_spans import RequestSpanMiddleware
from server_core.observability.spans import job_span
from server_core.observability.streams import NO_STREAMS, StreamRoutes
from server_core.testing.metrics import MetricsRecorder
from server_core.testing.spans import SpanRecorder

STREAMS = StreamRoutes.of(r'/api/v1/chat/conversations/[^/]+/messages')
STREAM_PATH = '/api/v1/chat/conversations/7f0c/messages'


async def answer(scope, receive, send) -> None:
    """응답을 시작하고 끝내는 앱."""
    await send({'type': 'http.response.start', 'status': 200, 'headers': []})
    await send({'type': 'http.response.body', 'body': b''})


async def ignore(message) -> None:
    return


def http_scope(path: str) -> dict:
    return {'type': 'http', 'method': 'POST', 'path': path, 'headers': []}


def bounds_of(metrics: MetricsRecorder, name: str) -> tuple[float, ...]:
    """그 이름의 히스토그램의 구간."""
    data = metrics.reader.get_metrics_data()
    point = next(
        metric.data.data_points[0]
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == name
    )
    return tuple(point.explicit_bounds)


# --- 스트림인 주소 ---


def test_a_stream_route_matches_the_whole_path():
    assert STREAMS.matches(STREAM_PATH)
    assert not STREAMS.matches(STREAM_PATH + '/extra')
    assert not STREAMS.matches('/api/v1/chat/conversations')
    assert not NO_STREAMS.matches(STREAM_PATH)


async def test_a_stream_gets_no_request_span(spans: SpanRecorder):
    await RequestSpanMiddleware(answer, streams=STREAMS)(http_scope(STREAM_PATH), None, ignore)

    assert spans.ended() == []


async def test_without_streams_the_same_path_gets_a_span(spans: SpanRecorder):
    # 스트림을 넘기지 않은 서버(알림, asset)는 모든 요청에 span 을 건다
    await RequestSpanMiddleware(answer)(http_scope(STREAM_PATH), None, ignore)

    assert spans.only().name == 'POST (unmatched)'


async def test_a_stream_is_counted_but_neither_timed_nor_active(metrics: MetricsRecorder):
    active_while_open: list[float | None] = []

    async def streaming(scope, receive, send) -> None:
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        active_while_open.append(metrics.value('http_server_active_requests'))

    await RequestMetricsMiddleware(streaming, streams=STREAMS)(http_scope(STREAM_PATH), None, ignore)

    # 몇 시간씩 열려 있는 스트림이 처리 중인 수와 시간 분포를 덮지 않는다. 스트림은 sse_* 가 센다
    assert active_while_open == [None]
    assert metrics.value('http_server_requests', status_code=200) == 1
    assert metrics.points('http_server_request_duration') == []


async def test_a_request_that_is_not_a_stream_is_timed(metrics: MetricsRecorder):
    await RequestMetricsMiddleware(answer, streams=STREAMS)(http_scope('/api/v1/chat/me'), None, ignore)

    assert metrics.value('http_server_request_duration', method='POST', route='(unmatched)') == 1


# --- SSE 연결 ---


def test_a_stream_connection_is_counted_until_it_ends(metrics: MetricsRecorder):
    with measured_stream():
        assert metrics.value('sse_connections') == 1

    assert metrics.value('sse_connections_opened') == 1
    assert metrics.value('sse_connections') == 0
    (duration,) = metrics.points('sse_connection_duration')
    assert (duration.unit, duration.value) == ('s', 1)
    assert bounds_of(metrics, 'sse_connection_duration') == STREAM_BUCKETS


def test_a_stream_cut_off_is_still_counted(metrics: MetricsRecorder):
    try:
        with measured_stream():
            raise ConnectionResetError
    except ConnectionResetError:
        pass

    assert metrics.value('sse_connections') == 0
    assert metrics.value('sse_connection_duration') == 1


# --- 서버가 더하는 계측기 ---


@dataclass(frozen=True)
class ProbeInstruments:
    received: Counter


def build_probe(meter: Meter) -> ProbeInstruments:
    return ProbeInstruments(received=meter.create_counter('probe_received', description='테스트의 셈'))


PROBE = InstrumentSet(build_probe)


def test_a_server_instrument_set_follows_the_provider(metrics: MetricsRecorder):
    # 모듈을 불러올 때 만든 묶음도 바꿔 끼운 것으로 다시 만들어진다
    PROBE.get().received.add(2, {'source': 'game'})

    assert metrics.value('probe_received', source='game') == 2


def test_after_recording_the_set_is_back_to_nothing():
    # 끼운 것이 없으면(NoOp) 세어도 아무 일이 없다
    PROBE.get().received.add(1)


# --- 작업의 span ---


def test_a_job_without_a_span_starts_its_own_trace(spans: SpanRecorder):
    with job_span('test.job', 'job-1'):
        pass

    assert spans.only().parent is None


def test_a_job_under_a_span_continues_its_trace(spans: SpanRecorder):
    # 요청이 맡긴 작업은 그 요청의 추적에 이어진다(게임 서버의 서술)
    with spans.parent() as parent, job_span('test.job', 'job-1'):
        pass

    job = spans.only()
    assert job.parent.span_id == parent.get_span_context().span_id
    assert job.context.trace_id == parent.get_span_context().trace_id
