# shared/server-core/tests/test_tracing_idle_rounds.py

"""
할 일이 없던 바퀴의 추적을 보내지 않는 것을 검증한다.
server_core/observability/idle_rounds.py 의 DropIdleRounds, spans.py 의 add_handled 와 job_span.

메모리에 모으는 것(server_core/testing/spans.py)이 서버와 같은 DropIdleRounds 를 거친다.
실제 바퀴(게임 서버의 시계, 청구 정리, 알림 보내기)는 그 서버의 테스트가 본다.
"""

import pytest
from opentelemetry.trace import StatusCode

from server_core.observability.spans import ATTRIBUTE_HANDLED, add_handled, job_span, tracer
from server_core.testing.spans import SpanRecorder


def query_span(name: str = 'db SELECT tables') -> None:
    """바퀴 안의 쿼리 하나만큼의 span."""
    tracer().start_span(name).end()


def round_of(handled: int | None, fail: bool = False) -> None:
    """작업 한 바퀴. 쿼리 하나를 남기고, 맡은 수를 더한다(None 이면 더하지 않는다)."""
    with job_span('round.close_overdue', 'job-1'):
        query_span()
        if handled is not None:
            add_handled(handled)
        if fail:
            raise RuntimeError('DB 가 없다')


def test_add_handled_outside_a_job_does_nothing(spans: SpanRecorder):
    add_handled(3)

    with job_span('round.narrate', 'job-1'):
        pass

    assert ATTRIBUTE_HANDLED not in spans.only().attributes


def test_job_span_carries_the_sum_of_handled(spans: SpanRecorder):
    with job_span('charge.settle', 'job-1'):
        add_handled(2)
        add_handled(0)
        add_handled(3)

    assert spans.only().attributes[ATTRIBUTE_HANDLED] == 5


def test_an_idle_round_is_dropped_with_its_queries(spans: SpanRecorder):
    round_of(0)

    assert spans.ended() == []


def test_a_round_that_took_something_is_kept_with_its_queries(spans: SpanRecorder):
    round_of(1)

    assert spans.names() == ['db SELECT tables', 'round.close_overdue']


def test_a_failed_round_is_kept_even_if_it_took_nothing(spans: SpanRecorder):
    with pytest.raises(RuntimeError):
        round_of(0, fail=True)

    assert spans.find('round.close_overdue').status.status_code == StatusCode.ERROR
    assert len(spans.ended()) == 2


def test_a_job_without_handled_is_kept(spans: SpanRecorder):
    round_of(None)

    assert len(spans.ended()) == 2


def test_a_round_under_a_request_is_not_held(spans: SpanRecorder):
    # 부모가 있는 작업(요청이 맡긴 것)은 그 요청의 추적이라 버리지 않는다
    with spans.parent():
        round_of(0)

    assert spans.names() == ['db SELECT tables', 'round.close_overdue']


def test_a_request_trace_passes_through_as_spans_end(spans: SpanRecorder):
    with spans.parent():
        query_span()
        assert spans.names() == ['db SELECT tables']
