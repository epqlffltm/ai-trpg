# auth-server/observability/tests/spans.py

"""
테스트가 남긴 span 을 읽는 도구.
메모리에 모으는 것을 끼우고(spans.use_provider), 테스트가 끝나면 아무것도 하지 않는 것으로 되돌린다.

남기는 규칙은 서버와 같다(tracing.SAMPLER). 할 일이 없던 바퀴를 버리는 것(idle_rounds.DropIdleRounds)도 같이 끼운다.
보내는 일(OTLP)은 하지 않는다. 보내는 길은 test_tracing_setup.py 가 본다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest import TestCase

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability.idle_rounds import DropIdleRounds
from observability.spans import tracer, use_provider
from observability.tracing import SAMPLER

# parent 가 거는 span 의 이름. 끝난 span 을 셀 때 뺀다
PARENT_NAME = 'test.parent'


class SpanRecorder:
    """테스트 하나가 남긴 span 을 모은다."""

    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider(sampler=SAMPLER)
        self.provider.add_span_processor(DropIdleRounds(SimpleSpanProcessor(self.exporter)))

    def ended(self) -> list[ReadableSpan]:
        """끝난 span 들. parent 가 건 것은 뺀다."""
        return [span for span in self.exporter.get_finished_spans() if span.name != PARENT_NAME]

    def names(self) -> list[str]:
        """끝난 span 의 이름들."""
        return [span.name for span in self.ended()]

    def find(self, name: str) -> ReadableSpan:
        """그 이름으로 끝난 span 이다. 하나여야 한다."""
        found = [span for span in self.ended() if span.name == name]
        assert len(found) == 1, f'span {name} 가 {len(found)} 개다: {self.names()}'
        return found[0]

    @contextmanager
    def parent(self) -> Iterator[trace.Span]:
        """기록 중인 span 하나를 건다. 요청이나 작업 안에서 도는 것을 흉내 낸다."""
        with tracer().start_as_current_span(PARENT_NAME) as span:
            yield span


def record_spans(test: TestCase) -> SpanRecorder:
    """그 테스트 동안 span 을 메모리에 모은다. 테스트가 끝나면 아무것도 하지 않는 것으로 되돌린다."""
    recorder = SpanRecorder()
    use_provider(recorder.provider)
    test.addCleanup(recorder.provider.shutdown)
    test.addCleanup(use_provider, trace.NoOpTracerProvider())
    return recorder


def hex_trace_id(span: ReadableSpan) -> str:
    """span 의 추적 번호(소문자 16진수 32자). 로그의 trace_id 와 같은 모양이다."""
    return trace.format_trace_id(span.context.trace_id)


def traceparent_of(span: ReadableSpan) -> str:
    """그 span 을 부모로 하는 traceparent. 표시(flags)는 SDK 가 정한 그대로다."""
    span_id = trace.format_span_id(span.context.span_id)
    return f'00-{hex_trace_id(span)}-{span_id}-{span.context.trace_flags:02x}'
