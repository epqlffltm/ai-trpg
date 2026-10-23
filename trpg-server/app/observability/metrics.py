# trpg-server/app/observability/metrics.py

"""
게임 서버만의 메트릭. AI 호출, 서술, 라운드, 결제 서버를 부른 것이다(docs/observability.md 의 "메트릭").

요청, DB, 뒤의 작업, SSE 연결의 메트릭은 공용 코드(server_core/observability/metrics.py)가 센다(#589).
이 계측기는 공용 코드가 열어 둔 자리(InstrumentSet)에 더한다. 메트릭을 모으는 것을 바꿔 끼우면 함께 다시 만들어진다.
세는 곳은 record_* 를 부른다.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from opentelemetry.metrics import Counter, Histogram, Meter, _Gauge  # 동기 gauge 의 타입. API 가 이 이름으로 내보낸다
from server_core.observability.metrics import LONG_DURATION_BUCKETS, InstrumentSet, duration_histogram

# 서술이 끝난 모양(round_narrations_total 의 result)
NARRATION_SUCCESS = 'success'
NARRATION_FAILURE = 'failure'

# 서술 전에 고르는 것 하나가 끝난 모양(round_context_part_duration_seconds 의 result, #628).
# 고르지 못해도 서술은 한다(빈 것으로). 시간이 다 된 것과 예외로 끝난 것을 나눈다
CONTEXT_SUCCESS = 'success'
CONTEXT_TIMEOUT = 'timeout'
CONTEXT_FAILURE = 'failure'


@dataclass(frozen=True)
class GameInstruments:
    """게임 서버만의 계측기 묶음. 이름에서 _total 과 단위를 뗀 것이다. Alloy 가 붙여 표의 이름이 된다."""

    ai_calls: Counter
    ai_call_duration: Histogram
    ai_tokens: Counter
    ai_fallbacks: Counter
    round_narrations: Counter
    round_narration_retries: Counter
    round_narration_duration: Histogram
    round_context_duration: Histogram
    round_context_part_duration: Histogram
    rounds_closed: Counter
    billing_calls: Counter
    narration_charges: _Gauge


def build_instruments(meter: Meter) -> GameInstruments:
    """meter 로 게임 서버의 계측기를 만든다."""
    return GameInstruments(
        ai_calls=meter.create_counter('ai_calls', description='AI 를 부른 수. 값은 AI 호출 기록의 것과 같다'),
        ai_call_duration=duration_histogram(
            meter, 'ai_call_duration', 'AI 를 한 번 부르는 데 걸린 시간', LONG_DURATION_BUCKETS
        ),
        ai_tokens=meter.create_counter('ai_tokens', description='쓴 토큰의 수'),
        ai_fallbacks=meter.create_counter('ai_fallbacks', description='모델이 실패해 다음 모델로 넘어간 수'),
        round_narrations=meter.create_counter('round_narrations', description='끝난 서술의 수'),
        round_narration_retries=meter.create_counter(
            'round_narration_retries', description='같은 모델로 서술을 다시 시도한 수'
        ),
        round_narration_duration=duration_histogram(
            meter, 'round_narration_duration', '라운드를 닫기 시작한 뒤 서술이 끝날 때까지', LONG_DURATION_BUCKETS
        ),
        round_context_duration=duration_histogram(
            meter, 'round_context_duration', '서술 전에 로어북, 지난 일, 인물의 이력, 참고 자료를 고르는 데 걸린 시간'
        ),
        round_context_part_duration=duration_histogram(
            meter, 'round_context_part_duration', '서술 전에 고르는 것 하나가 걸린 시간'
        ),
        rounds_closed=meter.create_counter('rounds_closed', description='닫기 시작한 라운드의 수'),
        billing_calls=meter.create_counter('billing_calls', description='결제 서버를 부른 수'),
        narration_charges=meter.create_gauge('narration_charges', description='끝나지 않은 청구의 수'),
    )


_instruments = InstrumentSet(build_instruments)


def game_instruments() -> GameInstruments:
    """지금 끼운 것의 게임 서버의 계측기."""
    return _instruments.get()


# --- AI 와 서술 ---


@dataclass(frozen=True)
class AiCall:
    """AI 호출 하나의 셀 것. 값은 호출 기록(ai_invocations)의 칸이다. 토큰 수는 모르면 None 이다."""

    operation: str
    provider: str
    model: str
    outcome: str
    seconds: float
    input_tokens: int | None
    output_tokens: int | None


def record_ai_call(call: AiCall) -> None:
    """AI 호출 하나를 센다. 수, 걸린 시간, 토큰이다."""
    measured = game_instruments()
    labels = {'operation': call.operation, 'provider': call.provider, 'model': call.model}
    measured.ai_calls.add(1, {**labels, 'outcome': call.outcome})
    measured.ai_call_duration.record(call.seconds, labels)
    tokens = {'input': call.input_tokens, 'output': call.output_tokens}
    for direction, count in tokens.items():
        if count:
            measured.ai_tokens.add(count, {'provider': call.provider, 'model': call.model, 'direction': direction})


def record_ai_fallback(operation: str, model: str) -> None:
    """model 이 실패해 다음 모델로 넘어간 것을 센다. model 은 넘어가기 전의(실패한) 모델이다."""
    game_instruments().ai_fallbacks.add(1, {'operation': operation, 'model': model})


def record_narration_retry() -> None:
    """서술을 같은 모델로 다시 시도한 것을 센다."""
    game_instruments().round_narration_retries.add(1)


def record_narration(result: str, seconds: float | None = None) -> None:
    """끝난 서술 하나를 센다. seconds 는 닫기 시작한 뒤 걸린 시간이다. 성공한 것만 준다."""
    measured = game_instruments()
    measured.round_narrations.add(1, {'result': result})
    if seconds is not None:
        measured.round_narration_duration.record(seconds)


def record_context(seconds: float) -> None:
    """서술 전에 고르는 일 전체가 걸린 시간. 로어북 다음의 셋은 함께 돌아, 넷을 더한 것보다 짧다."""
    game_instruments().round_context_duration.record(seconds)


def record_context_part(part: str, result: str, seconds: float) -> None:
    """고르는 것 하나(part: lore, memories, histories, references)가 걸린 시간과 끝난 모양."""
    game_instruments().round_context_part_duration.record(seconds, {'part': part, 'result': result})


def record_round_closed(reason: str) -> None:
    """닫기 시작한 라운드 하나를 센다. reason 은 닫은 까닭이다(all_declared, host, timeout)."""
    game_instruments().rounds_closed.add(1, {'reason': str(reason)})


# --- 서술 값 ---


def record_billing_call(operation: str, outcome: str) -> None:
    """결제 서버를 부른 것 하나를 센다. operation 은 hold, capture, release, extend 다."""
    game_instruments().billing_calls.add(1, {'operation': operation, 'outcome': outcome})


def record_charges(counts: Mapping[str, int]) -> None:
    """끝나지 않은 청구의 수를 상태마다 적는다. 없는 상태는 0 으로 준다(부르는 쪽이 모든 상태를 넣는다)."""
    measured = game_instruments()
    for status, count in counts.items():
        measured.narration_charges.set(count, {'status': status})
