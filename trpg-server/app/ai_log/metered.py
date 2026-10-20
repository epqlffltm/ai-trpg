# trpg-server/app/ai_log/metered.py

"""
AI 호출을 세는 기록장. 기록 하나를 받을 때마다 메트릭(ai_calls_total, ai_call_duration_seconds, ai_tokens_total)을
세고, 기록은 안의 기록장(DbCallLog)에 넘긴다. app/ai/calls.py 의 CallLog 모양을 따른다.

AI 를 부르는 코드(app/ai)는 메트릭을 모른다(tests/test_ai_boundary.py). 기록장을 하나 더 꽂아 밖에서 센다.
그래서 메트릭의 값은 호출 기록(ai_invocations)의 값과 같다. operation 은 기록의 purpose(narration)다.
안의 기록장이 실패해도(DB 가 내려감) 센다. 호출은 이미 시간과 토큰을 썼다.
"""

from dataclasses import dataclass

from app.ai.calls import CallLog, CallRecord
from app.observability.metrics import AiCall, record_ai_call


def ai_call_of(record: CallRecord) -> AiCall:
    """기록에서 셀 것을 꺼낸다. 걸린 시간은 초로 바꾼다."""
    return AiCall(
        operation=record.scope.purpose,
        provider=record.provider,
        model=record.model,
        outcome=record.outcome.value,
        seconds=record.latency_ms / 1000,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
    )


@dataclass(frozen=True)
class MeteredCallLog:
    """세고 넘기는 기록장. 쓰는 것은 inner 가 한다(app/rounds/narrator_setup.py)."""

    inner: CallLog

    async def write(self, record: CallRecord) -> None:
        """기록 하나를 안의 기록장에 쓰고 센다. 쓰다 실패해도 세고, 예외는 그대로 올린다."""
        try:
            await self.inner.write(record)
        finally:
            record_ai_call(ai_call_of(record))
