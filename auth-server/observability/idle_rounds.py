# auth-server/observability/idle_rounds.py

"""
할 일이 없던 작업의 추적을 보내지 않는 것. span 을 보내는 것(BatchSpanProcessor) 앞에 끼운다(tracing.py).

메일 워커와 환영 크레딧 워커는 1초마다 한 바퀴씩 돈다. 대개 할 일이 없다. 그 바퀴마다 추적을 남기면 하루에
수십만 개가 되고, Tempo 의 검색이 빈 바퀴로 메워진다. 한 일이 있는 바퀴와 실패한 바퀴만 남긴다.

작업의 span 이 끝나야 할 일이 있었는지 안다(spans.record_handled). 그 아래의 span(쿼리, 결제 서버를 부른 것)은
먼저 끝난다. 그래서 작업의 추적에 든 span 은 작업의 span 이 끝날 때까지 들고 있다가 함께 보내거나 함께 버린다.
작업이 아닌 추적(요청)은 들지 않고 바로 넘긴다.
"""

import threading

from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.trace import StatusCode

from observability.spans import ATTRIBUTE_HANDLED, ATTRIBUTE_JOB_ID


def is_job_root(span: ReadableSpan) -> bool:
    """부모 없이 시작한 작업의 span 인가. 그 추적은 끝날 때까지 들고 있는다."""
    return span.parent is None and ATTRIBUTE_JOB_ID in (span.attributes or {})


def is_idle(span: ReadableSpan) -> bool:
    """할 일이 없던 바퀴인가. 처리한 수가 0 이고 실패하지 않았다. 처리한 수를 적지 않은 작업은 남긴다."""
    return (span.attributes or {}).get(ATTRIBUTE_HANDLED) == 0 and span.status.status_code != StatusCode.ERROR


class DropIdleRounds(SpanProcessor):
    """할 일이 없던 작업의 추적을 버리고, 나머지는 inner 에 넘긴다."""

    def __init__(self, inner: SpanProcessor) -> None:
        self._inner = inner
        # 작업의 추적마다 먼저 끝난 span 들. 작업의 span 이 끝나면 비운다
        self._held: dict[int, list[ReadableSpan]] = {}
        self._lock = threading.Lock()

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        """작업의 span 이 시작하면 그 추적을 들고 있기 시작한다."""
        if is_job_root(span):
            with self._lock:
                self._held.setdefault(span.context.trace_id, [])
        self._inner.on_start(span, parent_context=parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        """끝난 span 을 들고 있거나, 작업이 끝났으면 함께 넘기거나 버린다."""
        released = self._release(span)
        if released is None or (is_job_root(span) and is_idle(span)):
            return
        for each in released:
            self._inner.on_end(each)

    def _release(self, span: ReadableSpan) -> list[ReadableSpan] | None:
        """
        지금 넘길 span 들. 작업의 추적에 든 span 이면 들고 있고 None 을 돌려준다.

        작업의 span 이면 들고 있던 것과 그것을 함께 돌려준다. 작업이 아닌 추적의 span 은 그것 하나다.
        """
        trace_id = span.context.trace_id
        with self._lock:
            held = self._held.get(trace_id)
            if held is None:
                return [span]
            if not is_job_root(span):
                held.append(span)
                return None
            del self._held[trace_id]
            return [*held, span]

    def shutdown(self) -> None:
        """끝나지 않은 작업의 추적은 버리고 inner 를 끈다."""
        with self._lock:
            self._held.clear()
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """inner 가 모아 둔 것을 보낸다."""
        return self._inner.force_flush(timeout_millis)
