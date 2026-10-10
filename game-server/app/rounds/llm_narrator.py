# game-server/app/rounds/llm_narrator.py

"""
언어 모델로 GM 의 서술을 쓰는 서술자. app/rounds/narrator.py 의 Narrator 모양을 따른다.

하는 일은 넷이다. 넷을 한 함수에 섞지 않는다.
  1. 메시지를 조립한다(app/rounds/prompt.py, 순수 함수).
  2. provider 를 부른다(app/ai/provider.py). 어느 모델인지는 모른다.
  3. 받은 글을 검사한다. 장면으로 쓸 수 있는 글만 돌려준다.
  4. 부른 것을 기록한다(app/ai/calls.py). 잘 끝났든, 글을 쓰지 않았든, 부르지 못했든 한 번에 하나.
     어디에 쓰는지는 모른다. 앱이 DB 에 쓰는 기록장을 꽂는다.

모델의 글은 장면이 될 뿐이다. 상태를 바꾸지 않는다. 결과(판정, HP, 죽음)는 엔진이 이미 정해 DB 에 적었다.
그래서 검사는 "장면으로 쓸 수 있는가"만 본다. 끊기지 않았고, 비어 있지 않고, 너무 길지 않은가.

한 번만 부른다. 실패하면 예외를 그대로 올린다.
다시 시도하기와 다른 모델로 넘어가기는 이 서술자를 감싸는 쪽이 한다(app/rounds/retrying_narrator.py).
"""

import time
from dataclasses import dataclass

from app.ai.calls import CallLog, CallRecord, CallScope, Outcome
from app.ai.provider import Completion, GenerationParams, LLMProvider, ProviderError
from app.rounds.narrator import NarrationRequest
from app.rounds.prompt import PROMPT_VERSION, build_messages

# 서술을 만들 때의 설정. 몇 문단의 장면이면 충분하다. 너무 딱딱하지 않게 조금 다양하게 쓴다
NARRATION_PARAMS = GenerationParams(max_tokens=800, temperature=0.8)

# 호출 기록에 적는 쓰임새
PURPOSE = 'narration'

# 장면으로 받는 글의 상한(글자 수). 다음 라운드의 요청에 다시 들어가므로, 길면 그만큼 다음 호출이 비싸진다
SCENE_MAX_LENGTH = 4000


class NarrationError(Exception):
    """서술자가 장면으로 쓸 글을 만들지 못했다. 글이 끊겼거나, 비었거나, 너무 길거나, 요청에 이야기의 바탕이 없다."""


def accept_scene(text: str) -> str:
    """
    모델의 글을 장면으로 받아도 되는지 보고, 앞뒤 공백을 뗀 글을 돌려준다. 안 되면 NarrationError.

    길이를 넘는 글을 잘라서 받지 않는다. 문장 중간에서 끊긴 장면이 기록으로 굳는다.
    """
    scene = text.strip()
    if not scene:
        raise NarrationError('empty')
    if len(scene) > SCENE_MAX_LENGTH:
        raise NarrationError('too_long')
    return scene


def accept_completion(completion: Completion) -> str:
    """
    provider 의 답을 장면으로 받는다. 안 되면 NarrationError.

    길이 상한에 걸려 끊긴 답은 받지 않는다. 너무 긴 글을 잘라 받지 않는 것과 같은 이유다.
    """
    if completion.truncated:
        raise NarrationError('cut_off')
    return accept_scene(completion.text)


def elapsed_ms(started: float) -> int:
    """started(time.perf_counter 의 값)부터 지금까지 걸린 시간(밀리초)."""
    return round((time.perf_counter() - started) * 1000)


def narration_scope(request: NarrationRequest) -> CallScope:
    """서술 요청에서 호출의 쓰임새와 테이블을 꺼낸다."""
    return CallScope(
        purpose=PURPOSE, table_id=request.table_id, round_number=request.round_number, host_id=request.host_id
    )


def outcome_of(completion: Completion | None, error: str | None) -> Outcome:
    """호출이 어떻게 끝났나. 답이 없으면 받지 못한 것, 답이 있는데 이유가 있으면 쓰지 않은 것이다."""
    if completion is None:
        return Outcome.FAILED
    if error is not None:
        return Outcome.REJECTED
    return Outcome.OK


@dataclass(frozen=True)
class LLMNarrator:
    """
    언어 모델로 서술하는 서술자. provider 를 바꿔 끼우면 다른 모델이 쓴다.

    log 는 호출을 기록하는 곳이다. 비워 둘 수 없다. 기록 없이 모델을 부르는 길을 만들지 않는다.
    """

    provider: LLMProvider
    log: CallLog
    params: GenerationParams = NARRATION_PARAMS

    def describe(
        self, request: NarrationRequest, latency_ms: int, completion: Completion | None = None, error: str | None = None
    ) -> CallRecord:
        """
        호출 한 번을 기록의 모양으로 만든다.

        답이 있으면 답에 적힌 모델의 이름을 쓴다. 없으면(받지 못했으면) provider 가 들고 있는 이름이다.
        """
        return CallRecord(
            scope=narration_scope(request),
            provider=self.provider.kind,
            model=completion.model if completion else self.provider.model,
            prompt_version=PROMPT_VERSION,
            reasoning=self.params.reasoning,
            outcome=outcome_of(completion, error),
            latency_ms=latency_ms,
            narration_style=request.style,
            error=error,
            input_tokens=completion.input_tokens if completion else None,
            output_tokens=completion.output_tokens if completion else None,
            finish_reason=completion.finish_reason if completion else None,
            text=completion.text if completion else None,
        )

    async def narrate(self, request: NarrationRequest) -> str:
        """
        닫힌 라운드의 결과를 서술한다. 돌려준 글이 다음 라운드의 장면이 된다.

        부르고 나면 어떻게 끝났든 기록을 하나 남기고, 실패면 그 예외를 그대로 올린다.
        이야기의 바탕이 없는 요청은 부르지 않는다. 부르지 않았으니 기록도 없다.
        """
        if request.story is None:
            raise NarrationError('no_story')
        messages = build_messages(request)
        started = time.perf_counter()
        try:
            completion = await self.provider.complete(messages, self.params)
        except ProviderError as error:
            await self.log.write(self.describe(request, elapsed_ms(started), error=str(error)))
            raise
        latency_ms = elapsed_ms(started)
        try:
            scene = accept_completion(completion)
        except NarrationError as error:
            await self.log.write(self.describe(request, latency_ms, completion, error=str(error)))
            raise
        await self.log.write(self.describe(request, latency_ms, completion))
        return scene
