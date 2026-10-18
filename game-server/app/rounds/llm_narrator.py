# game-server/app/rounds/llm_narrator.py

"""
언어 모델로 GM 의 서술을 쓰는 서술자. app/rounds/narrator.py 의 Narrator 모양을 따른다.

하는 일은 넷이다. 넷을 한 함수에 섞지 않는다.
  1. 입력 예산에 맞게 요청을 줄이고(app/rounds/budget.py) 메시지를 조립한다(app/rounds/prompt.py, 순수 함수).
     기록에는 줄인 요청이 넣은 로어북 항목과 기억을 적는다. 실제로 보낸 것이다.
  2. provider 를 부른다(app/ai/provider.py). 어느 모델인지는 모른다.
  3. 받은 글을 검사한다. 장면으로 쓸 수 있는 글만 돌려준다.
  4. 부른 것을 기록한다(app/ai/calls.py). 잘 끝났든, 글을 쓰지 않았든, 부르지 못했든 한 번에 하나.
     어디에 쓰는지는 모른다. 앱이 DB 에 쓰는 기록장을 꽂는다.
모델이 쓰는 대로 받은 조각은 미리 보기에 그대로 넘긴다. 검사하기 전의 글이다. 받지 않으면 버려지는 글이 된다.

모델의 글은 장면이 될 뿐이다. 상태를 바꾸지 않는다. 결과(판정, HP, 죽음)는 엔진이 이미 정해 DB 에 적었다.
그래서 검사는 "장면으로 쓸 수 있는가"만 본다. 비어 있지 않고, 너무 길지 않은가.
출력 상한에 걸려 끊긴 글은 마지막 문장까지 잘라 받는다. 그렇게 남은 글이 너무 짧을 때만 받지 않는다.

한 번만 부른다. 실패하면 예외를 그대로 올린다.
다시 시도하기와 다른 모델로 넘어가기는 이 서술자를 감싸는 쪽이 한다(app/rounds/retrying_narrator.py).
"""

import logging
import re
import time
from dataclasses import dataclass

from app.ai.calls import CallLog, CallRecord, CallScope, Outcome, chars_of, input_digest
from app.ai.costs import PriceTag, usage_of
from app.ai.provider import ChatMessage, Completion, GenerationParams, LLMProvider, ProviderError
from app.catalog.rules import ROUND_OUTPUT_TOKENS
from app.rounds.budget import INPUT_BUDGET, estimate_messages, fit_request
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview
from app.rounds.prompt import PROMPT_VERSION, build_messages

logger = logging.getLogger(__name__)

# 서술을 만들 때의 설정. 몇 문단의 장면이면 충분하다. 너무 딱딱하지 않게 조금 다양하게 쓴다.
# 출력 상한은 판매가가 가정한 출력(1,200 토큰)과 같다. 생각을 끌 수 없는 모델은 창구가 생각의 몫을 더한다
NARRATION_PARAMS = GenerationParams(max_tokens=ROUND_OUTPUT_TOKENS, temperature=0.8)

# 호출 기록에 적는 쓰임새
PURPOSE = 'narration'

# 장면으로 받는 글의 상한(글자 수). 다음 라운드의 요청에 다시 들어가므로, 길면 그만큼 다음 호출이 비싸진다
SCENE_MAX_LENGTH = 4000

# 출력 상한에 걸려 잘린 글을 마지막 문장까지 잘라 받을 때, 이보다 짧으면 받지 않고 다시 부른다(cut_off).
# 생각을 끌 수 없는 모델이 생각에 출력을 다 써서 본문이 거의 없는 경우가 여기에 걸린다
TRUNCATED_MIN_LENGTH = 300
# 문장의 끝. 마침표·느낌표·물음표·말줄임표 뒤에 닫는 따옴표나 괄호가 붙을 수 있다
SENTENCE_END = re.compile(r'[.!?…。]["\'”’」』)\]]*')


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


def trim_to_sentence(text: str) -> str:
    """마지막으로 끝난 문장까지만 남긴다. 끝난 문장이 없으면 빈 글이다."""
    ends = [match.end() for match in SENTENCE_END.finditer(text)]
    return text[: ends[-1]].strip() if ends else ''


def accept_truncated(text: str) -> str:
    """
    출력 상한에 걸려 잘린 글을 마지막 문장까지 잘라 장면으로 받는다. 너무 짧으면 NarrationError(cut_off).

    버리고 다시 부르면 같은 값을 한 번 더 내고, 같은 요청이라 또 잘리기 쉽다. 이어 쓰게 하면 출력이
    판매가가 가정한 양(1,200 토큰)을 넘는다. 그래서 끝난 문장까지만 받는다. 문장 중간에서 끊긴 글은 굳지 않는다.
    """
    scene = trim_to_sentence(text.strip())
    if len(scene) < TRUNCATED_MIN_LENGTH:
        raise NarrationError('cut_off')
    logger.warning('잘린 서술을 마지막 문장까지 받았다', extra={'result': 'truncated', 'kept_chars': len(scene)})
    return accept_scene(scene)


def accept_completion(completion: Completion) -> str:
    """
    provider 의 답을 장면으로 받는다. 안 되면 NarrationError.

    길이 상한에 걸려 끊긴 답은 마지막 문장까지 잘라 받는다(accept_truncated). 너무 짧으면 다시 부른다.
    """
    if completion.truncated:
        return accept_truncated(completion.text)
    return accept_scene(completion.text)


def elapsed_ms(started: float) -> int:
    """started(time.perf_counter 의 값)부터 지금까지 걸린 시간(밀리초)."""
    return round((time.perf_counter() - started) * 1000)


def narration_scope(request: NarrationRequest) -> CallScope:
    """서술 요청에서 호출의 쓰임새와 테이블을 꺼낸다."""
    return CallScope(
        purpose=PURPOSE, table_id=request.table_id, round_number=request.round_number, host_id=request.host_id
    )


def warn_if_over_budget(request: NarrationRequest, messages: list[ChatMessage]) -> None:
    """
    줄이고도 입력이 예산을 넘으면 경고를 남긴다. 빼지 않는 것(작가의 글, 이번 라운드)만으로 큰 때다.

    부르는 것은 막지 않는다. 라운드를 실패시키면 앉은 사람 모두가 멈춘다. 경고로 그런 판이 얼마나 되는지 본다.
    """
    tokens = estimate_messages(messages)
    if tokens <= INPUT_BUDGET:
        return
    logger.warning(
        '서술의 입력이 예산을 넘는다. 뺄 것을 다 빼고 그대로 부른다',
        extra={
            'table_id': str(request.table_id),
            'round_number': request.round_number,
            'estimated_tokens': tokens,
            'budget': INPUT_BUDGET,
        },
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
    digest_key 는 보낸 메시지의 지문(HMAC)을 만드는 키다. 없으면 지문을 남기지 않는다(app/ai/calls.py).
    price 는 모델 목록의 이름표와 그날의 단가다. 있으면 기록에 원가를 센다(app/ai/costs.py). 목록에 없는 모델이면 None.
    """

    provider: LLMProvider
    log: CallLog
    params: GenerationParams = NARRATION_PARAMS
    digest_key: bytes | None = None
    price: PriceTag | None = None

    def describe(
        self,
        request: NarrationRequest,
        latency_ms: int,
        completion: Completion | None = None,
        error: str | None = None,
        digest: str | None = None,
        input_chars: int | None = None,
    ) -> CallRecord:
        """
        호출 한 번을 기록의 모양으로 만든다. request 는 예산에 맞게 줄인 요청이다.

        답이 있으면 답에 적힌 모델의 이름을 쓴다. 없으면(받지 못했으면) provider 가 들고 있는 이름이다.
        생성 설정, 넣은 로어북 항목, 보낸 메시지의 지문(digest)과 글자 수(input_chars)를 함께 적는다.
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
            temperature=self.params.temperature,
            max_tokens=self.params.max_tokens,
            lore_entry_ids=tuple(note.entry_id for note in request.lore),
            memory_rounds=tuple(note.round_number for note in request.memories),
            input_digest=digest,
            input_chars=input_chars,
            usage=usage_of(completion, self.price),
        )

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        """
        닫힌 라운드의 결과를 서술한다. 돌려준 글이 다음 라운드의 장면이 된다.

        부르는 것이 시도 하나다. 부르기 전에 미리 보기를 새로 시작하고, 받는 조각을 넘긴다.
        부르고 나면 어떻게 끝났든 기록을 하나 남기고, 실패면 그 예외를 그대로 올린다.
        이야기의 바탕이 없는 요청은 부르지 않는다. 부르지 않았으니 기록도, 미리 보기도 없다.
        입력이 예산을 넘으면 덜 중요한 것부터 빼고 부른다(app/rounds/budget.py).
        """
        if request.story is None:
            raise NarrationError('no_story')
        sent = fit_request(request)
        messages = build_messages(sent)
        warn_if_over_budget(sent, messages)
        digest = input_digest(messages, self.digest_key)
        chars = chars_of(messages)
        preview.begin()
        started = time.perf_counter()
        try:
            completion = await self.provider.complete(messages, self.params, preview.text)
        except ProviderError as error:
            await self.log.write(
                self.describe(sent, elapsed_ms(started), error=str(error), digest=digest, input_chars=chars)
            )
            raise
        latency_ms = elapsed_ms(started)
        try:
            scene = accept_completion(completion)
        except NarrationError as error:
            await self.log.write(
                self.describe(sent, latency_ms, completion, error=str(error), digest=digest, input_chars=chars)
            )
            raise
        await self.log.write(self.describe(sent, latency_ms, completion, digest=digest, input_chars=chars))
        return scene
