# trpg-server/app/ai/gemini_stream.py

"""
Gemini(generateContent)의 흘려 받는 답을 읽는다. 네트워크를 모른다.
받은 줄들을 넣으면 답을 모으고, 새 글을 조각마다 넘긴다.

SSE 다(streamGenerateContent?alt=sse). 줄마다 'data: {...}' 에 응답 하나(GenerateContentResponse)가 온다.
  - candidates[0].content.parts[]: 새로 쓴 글(text). thought 가 참인 조각은 생각이다. 읽지 않는다.
  - candidates[0].finishReason: 멈춘 이유(STOP, MAX_TOKENS, SAFETY …). 마지막 조각에 온다.
  - promptFeedback.blockReason: 보낸 글이 막혔다. 글 없이 끝난다. 그 까닭을 멈춘 이유로 적는다.
  - usageMetadata: 토큰 수. 조각마다 올 수 있다. 마지막 것이 다 센 것이다. 온 칸만 바꾼다.
  - modelVersion: 답한 모델의 이름.
  - {"error": …}: 도중의 오류. ProviderError('stream_error'). 내용은 싣지 않는다.
[DONE] 같은 끝 표시가 없다. 멈춘 이유가 오지 않고 끝나면 도중에 끊긴 것이다(interrupted).

토큰 수는 OpenAI 의 뜻으로 바꿔 채운다(app/ai/provider.py 의 Completion).
  promptTokenCount 에는 캐시에서 읽은 것(cachedContentTokenCount)이 들어 있다. 그대로 쓴다.
  candidatesTokenCount 에는 생각(thoughtsTokenCount)이 빠져 있다.
  둘을 더한 것이 출력 전부다(생각도 출력으로 값이 매겨진다).
멈춘 이유가 MAX_TOKENS 면 길이 상한에 걸려 끊긴 것이다(truncated).
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.ai.provider import Completion, ProviderError, TextSink
from app.ai.streaming import data_of

# Gemini 에서 "길이 상한에 걸려 멈췄다"는 뜻의 멈춘 이유
MAX_TOKENS_FINISH = 'MAX_TOKENS'


def parse_response(data: str) -> dict[str, Any]:
    """데이터 하나(JSON)를 읽는다. 모양이 다르면 malformed, 오류 조각이면 stream_error 인 ProviderError."""
    try:
        response = json.loads(data)
    except ValueError as exc:
        raise ProviderError('malformed') from exc
    if not isinstance(response, dict):
        raise ProviderError('malformed')
    if 'error' in response:
        raise ProviderError('stream_error')
    return response


def first_candidate(response: dict[str, Any]) -> dict[str, Any]:
    """첫 후보. 없으면(막혔거나 토큰 수만 온 조각) 빈 것."""
    candidates = response.get('candidates') or []
    if not isinstance(candidates, list):
        raise ProviderError('malformed')
    return candidates[0] if candidates else {}


def text_of(candidate: dict[str, Any]) -> str:
    """후보에서 새로 쓴 글. 생각의 조각(thought)은 뺀다."""
    parts = (candidate.get('content') or {}).get('parts') or []
    pieces = []
    for part in parts:
        if not isinstance(part, dict):
            raise ProviderError('malformed')
        if part.get('thought'):
            continue
        text = part.get('text', '')
        if not isinstance(text, str):
            raise ProviderError('malformed')
        pieces.append(text)
    return ''.join(pieces)


@dataclass
class GeminiState:
    """
    지금까지 받은 것. 응답 조각을 더해 가다가 끝나면 답(Completion)으로 바꾼다.

    model 은 처음에 부른 모델의 이름이다. 조각에 답한 모델의 이름(modelVersion)이 오면 그것으로 바꾼다.
    """

    model: str
    text: str = ''
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    candidate_tokens: int | None = None
    thought_tokens: int | None = None

    def take_usage(self, usage: dict[str, Any]) -> None:
        """토큰 수 중 온 칸만 바꾼다. 나중에 온 것이 더 센 것이다."""
        if usage.get('promptTokenCount') is not None:
            self.prompt_tokens = usage['promptTokenCount']
        if usage.get('cachedContentTokenCount') is not None:
            self.cached_tokens = usage['cachedContentTokenCount']
        if usage.get('candidatesTokenCount') is not None:
            self.candidate_tokens = usage['candidatesTokenCount']
        if usage.get('thoughtsTokenCount') is not None:
            self.thought_tokens = usage['thoughtsTokenCount']

    def add(self, response: dict[str, Any]) -> str:
        """응답 조각 하나를 더한다. 새로 쓴 글을 돌려준다(없으면 빈 글)."""
        self.model = response.get('modelVersion') or self.model
        self.take_usage(response.get('usageMetadata') or {})
        blocked = (response.get('promptFeedback') or {}).get('blockReason')
        if blocked:
            self.finish_reason = blocked
        candidate = first_candidate(response)
        self.finish_reason = candidate.get('finishReason') or self.finish_reason
        piece = text_of(candidate)
        self.text += piece
        return piece

    def is_complete(self) -> bool:
        """끝까지 받았나. 멈춘 이유가 왔으면 끝까지 받은 것이다."""
        return self.finish_reason is not None

    def total_output(self) -> int | None:
        """쓴 출력 전부(OpenAI 의 뜻). 생각까지 더한다. 출력의 수를 모르면 None."""
        if self.candidate_tokens is None:
            return None
        return self.candidate_tokens + (self.thought_tokens or 0)

    def to_completion(self) -> Completion:
        """받은 것을 답으로 바꾼다."""
        return Completion(
            text=self.text,
            model=self.model,
            input_tokens=self.prompt_tokens,
            output_tokens=self.total_output(),
            finish_reason=self.finish_reason,
            truncated=self.finish_reason == MAX_TOKENS_FINISH,
            cached_input_tokens=self.cached_tokens,
            reasoning_tokens=self.thought_tokens,
        )


async def read_gemini_stream(lines: AsyncIterator[str], model: str, on_text: TextSink) -> Completion:
    """
    흘러오는 줄들을 끝까지 읽어 답을 만든다. 새 글은 오는 대로 on_text 에 넘긴다.

    끝 표시가 없어 줄이 다 올 때까지 읽는다. 멈춘 이유를 받지 못하고 끝나면 ProviderError('interrupted').
    """
    state = GeminiState(model)
    async for line in lines:
        data = data_of(line)
        if data is None:
            continue
        piece = state.add(parse_response(data))
        if piece:
            on_text(piece)
    if not state.is_complete():
        raise ProviderError('interrupted')
    return state.to_completion()
