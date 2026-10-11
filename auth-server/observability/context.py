# auth-server/observability/context.py

"""
지금 처리 중인 요청과 작업의 식별자를 들고 있는 곳.

contextvars 에 둔다. 함수마다 인자로 넘기지 않아도, 같은 요청을 처리하는 코드 어디서든 로그에 식별자가 붙는다.
요청을 처리하는 스레드마다(비동기로 돌면 작업마다) 이 값을 따로 들고 있어서, 동시에 처리되는 요청끼리 섞이지 않는다.

요청과 따로 도는 일(관리 명령으로 띄우는 메일 워커, 정리 작업)은 request_id 가 아니라 job_id 를 건다(job_scope).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from observability.identifiers import TRACEPARENT_HEADER, Trace, format_traceparent, new_trace

_request_id: ContextVar[str | None] = ContextVar('request_id', default=None)
_trace: ContextVar[Trace | None] = ContextVar('trace', default=None)
_job_id: ContextVar[str | None] = ContextVar('job_id', default=None)


def current_ids() -> dict[str, str]:
    """지금 걸려 있는 식별자들. 걸려 있지 않은 것은 싣지 않는다. 로그의 모든 줄에 붙는다."""
    trace = _trace.get()
    ids = {'request_id': _request_id.get(), 'trace_id': trace.trace_id if trace else None, 'job_id': _job_id.get()}
    return {name: value for name, value in ids.items() if value is not None}


def current_trace() -> Trace | None:
    """지금 걸려 있는 추적. 없으면 None 이다."""
    return _trace.get()


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

    걸려 있던 request_id 는 지운다. 작업은 요청이 아니다.
    추적은 걸려 있던 것을 이어 쓰고, 없으면(요청 밖에서 시작한 작업) 새로 시작한다.
    """
    job_token = _job_id.set(job_id)
    request_token = _request_id.set(None)
    trace_token = _trace.set(_trace.get() or new_trace())
    try:
        yield
    finally:
        _trace.reset(trace_token)
        _request_id.reset(request_token)
        _job_id.reset(job_token)


def outgoing_headers() -> dict[str, str]:
    """
    우리 서버끼리 부를 때 요청에 붙일 머리말. 추적을 이어 준다. 걸려 있는 추적이 없으면 비어 있다.

    request_id 는 넘기지 않는다. 받는 서버가 제 요청의 식별자를 따로 만든다. 둘은 trace_id 로 이어진다.
    밖의 서비스(메일 서버)를 부를 때는 붙이지 않는다. 우리 안의 식별자를 밖에 내보낼 까닭이 없다.
    지금 인증 서버는 다른 서버를 부르지 않는다. 부르게 되면 이 함수를 쓴다.
    """
    trace = _trace.get()
    return {TRACEPARENT_HEADER: format_traceparent(trace)} if trace else {}
