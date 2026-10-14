# game-server/app/drafts/writer.py

"""
모델에게 장부 초안을 받는다. 서술자(app/rounds/llm_narrator.py)와 같은 틀이다.

하는 일은 다섯이다. 한 함수에 섞지 않는다.
  1. 초안에 적을 거리가 있는지 본다. 없으면 부르지 않는다(app/drafts/context.py 의 has_choices).
  2. 메시지를 조립한다(app/drafts/prompt.py).
  3. provider 를 부른다. 어느 모델인지는 모른다.
  4. 답을 읽고(app/drafts/output.py) 테이블의 상태에 대어 본다(app/drafts/validation.py).
  5. 부른 것을 기록한다(app/ai/calls.py). 어떻게 끝났든 한 번에 하나.

초안은 덤이다. 서술과 달리 실패해도 예외를 올리지 않고 빈 결과(NOTHING)를 돌려준다.
모델이 죽었거나 답이 엉망이면 방장이 손으로 하던 대로 하면 된다. 실패는 기록에 남는다.
"""

import time
import uuid
from dataclasses import dataclass

from app.ai.calls import CallLog, CallRecord, CallScope, Outcome, input_digest
from app.ai.provider import Completion, GenerationParams, LLMProvider, ProviderError
from app.drafts.context import DraftContext, has_choices
from app.drafts.output import OutputError, read_output
from app.drafts.prompt import DRAFT_PROMPT_VERSION, build_messages
from app.drafts.validation import NOTHING, Checked, check_output

# 초안을 쓸 때의 설정. 고르는 일이라 온도는 0, 답은 짧은 JSON 하나다
DRAFT_PARAMS = GenerationParams(max_tokens=400, temperature=0.0)

# 호출 기록에 적는 쓰임새
PURPOSE = 'ledger_draft'


@dataclass(frozen=True)
class DraftRequest:
    """초안을 부탁할 것. 방금 쓴 장면과 고를 수 있는 목록, 그리고 기록에 적을 테이블과 라운드."""

    scene: str
    context: DraftContext
    table_id: uuid.UUID | None = None
    round_number: int | None = None
    host_id: uuid.UUID | None = None


def elapsed_ms(started: float) -> int:
    """started(time.perf_counter 의 값)부터 지금까지 걸린 시간(밀리초)."""
    return round((time.perf_counter() - started) * 1000)


def outcome_of(completion: Completion | None, error: str | None) -> Outcome:
    """호출이 어떻게 끝났나. 답이 없으면 받지 못한 것, 답이 있는데 이유가 있으면 쓰지 않은 것이다."""
    if completion is None:
        return Outcome.FAILED
    if error is not None:
        return Outcome.REJECTED
    return Outcome.OK


def read_completion(completion: Completion, context: DraftContext) -> Checked:
    """답을 읽고 대어 본다. 끊긴 답이면 OutputError(cut_off), 읽지 못하면 OutputError(not_json, bad_shape)."""
    if completion.truncated:
        raise OutputError('cut_off')
    return check_output(read_output(completion.text), context)


@dataclass(frozen=True)
class DraftWriter:
    """
    언어 모델로 장부 초안을 받는 것. provider 를 바꿔 끼우면 다른 모델이 고른다.

    log 는 호출을 기록하는 곳이다. 비워 둘 수 없다. digest_key 는 보낸 메시지의 지문(HMAC)을 만드는 키다.
    """

    provider: LLMProvider
    log: CallLog
    params: GenerationParams = DRAFT_PARAMS
    digest_key: bytes | None = None

    def describe(
        self,
        request: DraftRequest,
        latency_ms: int,
        completion: Completion | None = None,
        error: str | None = None,
        digest: str | None = None,
    ) -> CallRecord:
        """호출 한 번을 기록의 모양으로 만든다."""
        return CallRecord(
            scope=CallScope(PURPOSE, request.table_id, request.round_number, request.host_id),
            provider=self.provider.kind,
            model=completion.model if completion else self.provider.model,
            prompt_version=DRAFT_PROMPT_VERSION,
            reasoning=self.params.reasoning,
            outcome=outcome_of(completion, error),
            latency_ms=latency_ms,
            error=error,
            input_tokens=completion.input_tokens if completion else None,
            output_tokens=completion.output_tokens if completion else None,
            finish_reason=completion.finish_reason if completion else None,
            text=completion.text if completion else None,
            temperature=self.params.temperature,
            max_tokens=self.params.max_tokens,
            input_digest=digest,
        )

    async def draft(self, request: DraftRequest) -> Checked:
        """
        장면에서 장부 초안을 받는다. 받은 것과 버린 것을 돌려준다.

        초안에 적을 거리가 없으면 부르지 않는다(기록도 없다). 부르지 못했거나 답을 읽지 못하면 NOTHING 이다.
        """
        if not has_choices(request.context):
            return NOTHING
        messages = build_messages(request.scene, request.context)
        digest = input_digest(messages, self.digest_key)
        started = time.perf_counter()
        try:
            completion = await self.provider.complete(messages, self.params)
        except ProviderError as error:
            await self.log.write(self.describe(request, elapsed_ms(started), error=str(error), digest=digest))
            return NOTHING
        latency_ms = elapsed_ms(started)
        try:
            checked = read_completion(completion, request.context)
        except OutputError as error:
            await self.log.write(self.describe(request, latency_ms, completion, error=error.reason, digest=digest))
            return NOTHING
        await self.log.write(self.describe(request, latency_ms, completion, digest=digest))
        return checked
