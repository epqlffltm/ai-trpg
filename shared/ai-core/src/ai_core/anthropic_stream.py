# shared/ai-core/src/ai_core/anthropic_stream.py

"""
Claude(Anthropic Messages)의 흘려 받는 답을 읽는다. 네트워크를 모른다.
받은 줄들을 넣으면 답을 모으고, 새 글을 조각마다 넘긴다.

SSE 다. 'event: …' 줄과 'data: {...}' 줄이 온다. data 의 type 이 event 와 같아서 data 만 읽는다.
  - message_start: 답한 모델의 이름과 입력의 토큰 수
    (input_tokens, cache_creation_input_tokens, cache_read_input_tokens).
  - content_block_delta: delta.type 이 text_delta 면 새로 쓴 글이다.
    thinking_delta, signature_delta 는 생각이다. 읽지 않는다.
  - message_delta: 멈춘 이유(delta.stop_reason)와 토큰 수. 토큰 수는 그때까지의 누적이다. 온 칸만 바꾼다.
  - message_stop: 끝.
  - error: 도중의 오류(과부하 같은 것). ProviderError('stream_error'). 내용은 싣지 않는다.
  - ping, content_block_start, content_block_stop, 모르는 type: 넘어간다. 공급자가 새 type 을 더할 수 있다.
message_stop 도 멈춘 이유도 오지 않고 끝나면 도중에 끊긴 것이다(interrupted).

토큰 수는 OpenAI 의 뜻으로 바꿔 채운다(ai_core/provider.py 의 Completion).
  Claude 의 input_tokens 에는 캐시에서 읽은 것과 캐시에 쓴 것이 빠져 있다. 셋을 더한 것이 보낸 입력 전부다.
  출력(output_tokens)에는 생각에 쓴 것이 들어 있다. 생각만 따로 세어 주지 않아서 reasoning_tokens 는 비워 둔다.
멈춘 이유가 max_tokens 면 길이 상한에 걸려 끊긴 것이다(truncated).
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from ai_core.provider import Completion, ProviderError, TextSink
from ai_core.streaming import data_of

# Claude 에서 "길이 상한에 걸려 멈췄다"는 뜻의 멈춘 이유
MAX_TOKENS_STOP = 'max_tokens'
# 새로 쓴 글의 조각
TEXT_DELTA = 'text_delta'


def parse_event(data: str) -> dict[str, Any]:
    """데이터 하나(JSON)를 읽는다. 모양이 다르면 malformed, 오류 이벤트면 stream_error 인 ProviderError."""
    try:
        event = json.loads(data)
    except ValueError as exc:
        raise ProviderError('malformed') from exc
    if not isinstance(event, dict) or not isinstance(event.get('type'), str):
        raise ProviderError('malformed')
    if event['type'] == 'error':
        raise ProviderError('stream_error')
    return event


def text_of(event: dict[str, Any]) -> str:
    """content_block_delta 에서 새로 쓴 글. 글이 아니면(생각, 서명) 빈 글."""
    delta = event.get('delta') or {}
    if delta.get('type') != TEXT_DELTA:
        return ''
    text = delta.get('text')
    if not isinstance(text, str):
        raise ProviderError('malformed')
    return text


@dataclass
class ClaudeState:
    """
    지금까지 받은 것. 이벤트를 더해 가다가 끝나면 답(Completion)으로 바꾼다.

    model 은 처음에 부른 모델의 이름이다. message_start 에 답한 모델의 이름이 오면 그것으로 바꾼다.
    토큰 수는 Claude 의 뜻 그대로 들고 있다가 답으로 바꿀 때 OpenAI 의 뜻으로 옮긴다.
    """

    model: str
    text: str = ''
    stop_reason: str | None = None
    input_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cache_read_tokens: int | None = None
    output_tokens: int | None = None
    done: bool = False

    def take_usage(self, usage: dict[str, Any]) -> None:
        """토큰 수 중 온 칸만 바꾼다. message_delta 의 수는 누적이라 덮어쓴다."""
        if usage.get('input_tokens') is not None:
            self.input_tokens = usage['input_tokens']
        if usage.get('cache_creation_input_tokens') is not None:
            self.cache_creation_tokens = usage['cache_creation_input_tokens']
        if usage.get('cache_read_input_tokens') is not None:
            self.cache_read_tokens = usage['cache_read_input_tokens']
        if usage.get('output_tokens') is not None:
            self.output_tokens = usage['output_tokens']

    def add(self, event: dict[str, Any]) -> str:
        """이벤트 하나를 더한다. 새로 쓴 글을 돌려준다(없으면 빈 글)."""
        kind = event['type']
        if kind == 'message_start':
            message = event.get('message') or {}
            self.model = message.get('model') or self.model
            self.take_usage(message.get('usage') or {})
        elif kind == 'content_block_delta':
            piece = text_of(event)
            self.text += piece
            return piece
        elif kind == 'message_delta':
            self.stop_reason = (event.get('delta') or {}).get('stop_reason') or self.stop_reason
            self.take_usage(event.get('usage') or {})
        elif kind == 'message_stop':
            self.done = True
        return ''

    def is_complete(self) -> bool:
        """끝까지 받았나. message_stop 이 왔거나 멈춘 이유가 왔으면 끝까지 받은 것이다."""
        return self.done or self.stop_reason is not None

    def total_input(self) -> int | None:
        """보낸 입력 전부(OpenAI 의 뜻). 입력의 수를 모르면 None."""
        if self.input_tokens is None:
            return None
        return self.input_tokens + (self.cache_creation_tokens or 0) + (self.cache_read_tokens or 0)

    def to_completion(self) -> Completion:
        """받은 것을 답으로 바꾼다."""
        return Completion(
            text=self.text,
            model=self.model,
            input_tokens=self.total_input(),
            output_tokens=self.output_tokens,
            finish_reason=self.stop_reason,
            truncated=self.stop_reason == MAX_TOKENS_STOP,
            cached_input_tokens=self.cache_read_tokens,
            cache_write_tokens=self.cache_creation_tokens,
        )


async def read_claude_stream(lines: AsyncIterator[str], model: str, on_text: TextSink) -> Completion:
    """
    흘러오는 줄들을 끝까지 읽어 답을 만든다. 새 글은 오는 대로 on_text 에 넘긴다.

    message_stop 을 보면 그만 읽는다. 끝까지 받지 못하고 줄이 끝나면 ProviderError('interrupted').
    """
    state = ClaudeState(model)
    async for line in lines:
        data = data_of(line)
        if data is None:
            continue
        piece = state.add(parse_event(data))
        if piece:
            on_text(piece)
        if state.done:
            break
    if not state.is_complete():
        raise ProviderError('interrupted')
    return state.to_completion()
