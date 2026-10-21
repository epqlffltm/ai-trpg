# asset-server/app/observability/context.py

"""
지금 처리 중인 요청과 작업의 식별자를 들고 있는 곳.

contextvars 에 둔다. 함수마다 인자로 넘기지 않아도, 같은 요청을 처리하는 코드 어디서든 로그에 식별자가 붙는다.
asyncio 는 작업(task)마다 이 값을 따로 들고 있어서, 동시에 처리되는 요청끼리 섞이지 않는다.

요청이 뒤에서 도는 작업을 시작하면(asyncio.create_task) 작업은 시작한 쪽의 값을 물려받는다.
작업은 요청이 끝난 뒤에도 돈다. 그래서 작업 안에서는 request_id 를 지우고 job_id 를 건다(job_scope).
trace_id 는 그대로 둔다. 어느 요청에서 비롯된 작업인지 이을 수 있다.

span 이 걸려 있으면(spans.py) 추적은 그 span 의 것이다. 미들웨어가 요청의 추적을 정할 때 span 을 먼저 본다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.observability.identifiers import TRACEPARENT_HEADER, Trace, format_traceparent, new_trace
from app.observability.spans import span_trace, span_traceparent

_request_id: ContextVar[str | None] = ContextVar('request_id', default=None)
_trace: ContextVar[Trace | None] = ContextVar('trace', default=None)
_job_id: ContextVar[str | None] = ContextVar('job_id', default=None)


def current_ids() -> dict[str, str]:
    """지금 걸려 있는 식별자들. 걸려 있지 않은 것은 싣지 않는다. 로그의 모든 줄에 붙는다."""
    trace = _trace.get()
    ids = {'request_id': _request_id.get(), 'trace_id': trace.trace_id if trace else None, 'job_id': _job_id.get()}
    return {name: value for name, value in ids.items() if value is not None}


@contextmanager
def request_scope(request_id: str, trace: Trace) -> Iterator[None]:
    """요청 하나를 처리하는 동안 그 식별자들을 건다. 나가면 원래대로 돌린다."""
    request_token = _request_id.set(request_id)
    trace_token = _trace.set(trace)
    try:
        yield
    finally:
        _trace.reset(trace_token)
        _request_id.reset(request_token)


@contextmanager
def job_scope(job_id: str) -> Iterator[None]:
    """
    작업 하나가 도는 동안 그 식별자를 건다.

    작업을 시작한 요청의 request_id 는 지운다. 작업은 그 요청이 아니다.
    추적은 물려받은 것을 이어 쓴다. 없으면(요청 밖에서 시작한 작업) 작업의 span 의 것을(spans.job_span),
    그것도 없으면 새로 시작한다.
    """
    job_token = _job_id.set(job_id)
    request_token = _request_id.set(None)
    trace_token = _trace.set(_trace.get() or span_trace() or new_trace())
    try:
        yield
    finally:
        _trace.reset(trace_token)
        _request_id.reset(request_token)
        _job_id.reset(job_token)


def outgoing_headers() -> dict[str, str]:
    """
    우리 서버끼리 부를 때 요청에 붙일 머리말. 추적을 이어 준다. 걸려 있는 추적이 없으면 비어 있다.
    span 이 걸려 있으면 그 span 을 부모로 붙인다. 받는 서버의 span 이 그 아래에 이어진다.

    request_id 는 넘기지 않는다. 받는 서버가 제 요청의 식별자를 따로 만든다. 둘은 trace_id 로 이어진다.
    밖의 서비스(AI provider)를 부를 때는 붙이지 않는다. 우리 안의 식별자를 밖에 내보낼 까닭이 없다.
    """
    traceparent = span_traceparent()
    if traceparent is not None:
        return {TRACEPARENT_HEADER: traceparent}
    trace = _trace.get()
    return {TRACEPARENT_HEADER: format_traceparent(trace)} if trace else {}
