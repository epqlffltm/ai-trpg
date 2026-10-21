# asset-server/app/observability/spans.py

"""
추적(span)을 거는 곳이 함께 쓰는 것. OpenTelemetry 의 API 만 쓴다. 내보내는 일(SDK)은 tracing.py 가 한다.

span 을 만드는 것(TracerProvider)은 이 모듈에 하나 둔다. 처음에는 아무것도 하지 않는 것(NoOp)이다.
보낼 곳이 있으면 서버가 뜰 때 바꿔 끼운다(tracing.py 의 configure_tracing). 테스트는 메모리에 모으는 것을 끼운다.
OpenTelemetry 의 전역(trace.set_tracer_provider)은 한 번만 바꿀 수 있어서, 테스트가 바꿔 끼울 수 있게 따로 둔다.

span 이 있으면 로그의 trace_id 와 다른 서버에 넘기는 traceparent 가 그 span 의 것이 된다(context.py).
span 이 없으면(보낼 곳이 없는 PC) 지금처럼 context.py 가 정한 것을 쓴다.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, SpanKind, StatusCode, TraceFlags, TracerProvider

from app.observability.identifiers import Trace, traceparent_parts

# span 을 만드는 쪽의 이름. 서비스 이름과 같다
SCOPE_NAME = 'asset-server'
# span 에 싣는 우리 식별자의 이름. 로그의 칸과 같은 이름이라 Tempo 에서 같은 말로 찾는다(span.request_id).
# OpenTelemetry 에 없는 개념이라 정해진 이름이 없다
ATTRIBUTE_REQUEST_ID = 'request_id'
ATTRIBUTE_JOB_ID = 'job_id'
ATTRIBUTE_RESULT = 'result'
# 작업이 실패했을 때 span 의 설명. 로그의 error_code 와 같다. 오류의 글은 로그에만 있다
JOB_FAILED_ERROR_CODE = 'job.failed'

_provider: TracerProvider = trace.NoOpTracerProvider()


def use_provider(provider: TracerProvider) -> None:
    """span 을 만드는 것을 바꿔 끼운다. 서버가 뜰 때(tracing.py)와 테스트가 부른다."""
    global _provider
    _provider = provider


def tracer() -> trace.Tracer:
    """span 을 만드는 것. 끼워 둔 TracerProvider 를 따른다."""
    return _provider.get_tracer(SCOPE_NAME)


def is_recording() -> bool:
    """지금 기록 중인 span 안인가. 아니면 요청이나 작업 밖이다. 그 밖의 호출과 쿼리는 span 을 걸지 않는다."""
    return trace.get_current_span().is_recording()


def remote_parent(value: str | None) -> Context | None:
    """
    받은 traceparent 를 span 의 부모로 바꾼다. 받는 규칙은 parse_traceparent 와 같다(identifiers.py).

    형식에 맞지 않으면 None 이다. 그때는 부모 없이 새 추적을 시작한다.
    """
    parts = traceparent_parts(value)
    if parts is None:
        return None
    trace_id, span_id, flags = parts
    parent = SpanContext(
        trace_id=int(trace_id, 16), span_id=int(span_id, 16), is_remote=True, trace_flags=TraceFlags(int(flags, 16))
    )
    return trace.set_span_in_context(NonRecordingSpan(parent), Context())


def span_trace() -> Trace | None:
    """지금 걸린 span 의 추적. 로그의 trace_id 가 된다. span 이 없으면 None 이다."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return Trace(trace_id=trace.format_trace_id(context.trace_id), flags=f'{context.trace_flags:02x}')


def span_traceparent() -> str | None:
    """
    지금 걸린 span 을 부모로 하는 traceparent. 받는 서버의 span 이 이 span 아래에 붙는다. span 이 없으면 None 이다.
    """
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    trace_id = trace.format_trace_id(context.trace_id)
    span_id = trace.format_span_id(context.span_id)
    return f'00-{trace_id}-{span_id}-{context.trace_flags:02x}'


def tag_current_span(name: str, value: str) -> None:
    """지금 걸린 span 에 속성 하나를 싣는다. span 이 없으면 아무것도 하지 않는다."""
    trace.get_current_span().set_attribute(name, value)


def mark_job(span: Span, result: str) -> None:
    """작업이 끝난 모양을 span 에 적는다. 실패만 오류로 표시한다."""
    span.set_attribute(ATTRIBUTE_RESULT, result)
    if result == 'server_error':
        span.set_status(StatusCode.ERROR, JOB_FAILED_ERROR_CODE)


@contextmanager
def job_span(operation: str, job_id: str) -> Iterator[Span]:
    """
    작업 한 바퀴의 span. 이름은 operation 이다. 새 추적으로 시작한다.

    정리 작업은 한 시간마다 돈다. 서버가 뜬 흐름 아래에 두면 한 추적이 끝없이 길어진다.
    그 안의 쿼리가 이 span 아래에 놓이고, 로그의 trace_id 가 이 span 의 것이 된다(job_scope 를 이 안에서 건다).
    예외의 글은 span 에 싣지 않는다(DB 주소가 섞일 수 있다). 끝난 모양(result)과 오류 표시만 남긴다.
    """
    with tracer().start_as_current_span(
        operation,
        context=Context(),
        kind=SpanKind.INTERNAL,
        attributes={ATTRIBUTE_JOB_ID: job_id},
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except Exception:
            mark_job(span, 'server_error')
            raise
        except BaseException:
            # 끄느라 멈춘 것(CancelledError)은 실패가 아니다
            mark_job(span, 'cancelled')
            raise
        mark_job(span, 'success')
