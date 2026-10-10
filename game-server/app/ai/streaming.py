# game-server/app/ai/streaming.py

"""
흘려 받는 답(스트리밍)을 읽는다. 네트워크를 모른다. 받은 줄들을 넣으면 답을 모으고, 새 글을 조각마다 넘긴다.

OpenAI 모양의 스트리밍은 SSE 다. 줄마다 'data: {...}' 가 오고, 끝에 'data: [DONE]' 이 온다.
  - 조각마다 choices[0].delta.content 에 새로 쓴 글이 있다.
  - 멈춘 이유(finish_reason)는 마지막 글 조각에 온다.
  - 토큰 수(usage)는 맨 끝의 choices 가 빈 조각에 온다. 요청에 stream_options.include_usage 를 실어야 온다.
    싣지 않거나 모르는 서버면 오지 않는다. 그때는 토큰 수가 비어 있다.
  - 도중에 서버가 오류를 만나면 {"error": ...} 조각이 온다.
[DONE] 도 멈춘 이유도 오지 않고 끝나면 도중에 끊긴 것이다. 받은 데까지를 답으로 치지 않는다.

생각 글 걸러 내기.
  content 에 <think>...</think> 가 섞여 오는 모델이 있다. 다 받은 뒤라면 떼어 내면 그만이다(drop_thinking).
  흘려 보낼 때는 조각이 태그의 중간에서 끊길 수 있다("<thi" 다음 조각이 "nk>").
  그래서 지금까지 받은 글 전체에서 생각 글을 떼고, 끝에 걸친 태그의 앞부분은 다음 조각을 볼 때까지 붙잡아 둔다.
  넘긴 조각을 모두 이어 붙이면, 다 받은 뒤에 떼어 낸 글과 같다.
"""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.ai.provider import Completion, ProviderError, TextSink

# content 에 섞여 온 생각 글. 닫힌 것, 그리고 닫히지 않은 채 끝까지 간 것
THINKING_PATTERN = re.compile(r'<think>.*?(?:</think>|$)', re.DOTALL)
THINKING_OPEN = '<think>'

# SSE 의 데이터 줄의 머리와, 다 보냈다는 표시
DATA_PREFIX = 'data:'
DONE = '[DONE]'

# OpenAI 모양에서 "길이 상한에 걸려 멈췄다"는 뜻의 멈춘 이유
LENGTH_FINISH = 'length'


def drop_thinking(text: str) -> str:
    """content 에 섞여 온 생각 글을 떼어 낸다. 닫히지 않은 생각 글은 끝까지가 생각이다."""
    return THINKING_PATTERN.sub('', text)


def partial_open_tag(text: str) -> int:
    """글의 끝에 걸쳐 있는 생각 태그의 앞부분의 길이. '…<thi' 면 4 다. 없으면 0."""
    for size in range(len(THINKING_OPEN) - 1, 0, -1):
        if text.endswith(THINKING_OPEN[:size]):
            return size
    return 0


@dataclass
class ThinkingFilter:
    """
    흘러오는 글에서 생각 글을 걸러 낸다. 조각을 넣으면 내보내도 되는 새 글을 돌려준다.

    raw 는 지금까지 받은 글 전부, sent 는 지금까지 내보낸 글자 수다.
    """

    raw: str = ''
    sent: int = 0

    def feed(self, piece: str) -> str:
        """조각 하나를 받는다. 끝에 걸친 태그의 앞부분은 붙잡아 두고, 그 앞까지의 새 글을 돌려준다."""
        self.raw += piece
        visible = drop_thinking(self.raw)
        return self.take(visible[: len(visible) - partial_open_tag(visible)])

    def finish(self) -> str:
        """다 받았다. 붙잡아 둔 것까지 남은 글을 돌려준다. 끝까지 태그가 되지 않은 '<thi' 는 그냥 글이다."""
        return self.take(drop_thinking(self.raw))

    def take(self, visible: str) -> str:
        """보여도 되는 글 중 아직 내보내지 않은 뒷부분을 돌려주고, 내보낸 것으로 센다."""
        new = visible[self.sent :]
        self.sent += len(new)
        return new


@dataclass(frozen=True)
class Chunk:
    """조각 하나에서 읽은 것. 조각마다 있는 것만 채워져 있다."""

    text: str = ''
    model: str | None = None
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


def data_of(line: str) -> str | None:
    """SSE 의 한 줄에서 데이터를 꺼낸다. 데이터 줄이 아니면(빈 줄, 주석, 다른 칸) None."""
    if not line.startswith(DATA_PREFIX):
        return None
    return line.removeprefix(DATA_PREFIX).strip()


def parse_chunk(data: str) -> Chunk:
    """
    데이터 하나(JSON)를 조각으로 읽는다. 모양이 다르면 ProviderError('malformed').

    서버가 도중에 보낸 오류 조각은 ProviderError('stream_error') 다. 오류의 내용은 싣지 않는다.
    생각 글(delta.reasoning 칸)은 읽지 않는다.
    """
    try:
        body = json.loads(data)
    except ValueError as exc:
        raise ProviderError('malformed') from exc
    if isinstance(body, dict) and 'error' in body:
        raise ProviderError('stream_error')
    try:
        choices = body['choices']
        choice = choices[0] if choices else {}
        text = (choice.get('delta') or {}).get('content') or ''
        usage = body.get('usage') or {}
        chunk = Chunk(
            text=text,
            model=body.get('model'),
            finish_reason=choice.get('finish_reason'),
            input_tokens=usage.get('prompt_tokens'),
            output_tokens=usage.get('completion_tokens'),
        )
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ProviderError('malformed') from exc
    if not isinstance(text, str):
        raise ProviderError('malformed')
    return chunk


@dataclass
class StreamState:
    """
    지금까지 받은 것. 조각을 더해 가다가 끝나면 답(Completion)으로 바꾼다.

    model 은 처음에 부른 모델의 이름이다. 조각에 답한 모델의 이름이 오면 그것으로 바꾼다.
    """

    model: str
    thinking: ThinkingFilter = field(default_factory=ThinkingFilter)
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    done: bool = False

    def add(self, chunk: Chunk) -> str:
        """조각 하나를 더한다. 내보내도 되는 새 글을 돌려준다."""
        if chunk.model:
            self.model = chunk.model
        if chunk.finish_reason is not None:
            self.finish_reason = chunk.finish_reason
        if chunk.input_tokens is not None:
            self.input_tokens = chunk.input_tokens
        if chunk.output_tokens is not None:
            self.output_tokens = chunk.output_tokens
        return self.thinking.feed(chunk.text)

    def is_complete(self) -> bool:
        """끝까지 받았나. [DONE] 이 왔거나 멈춘 이유가 왔으면 끝까지 받은 것이다."""
        return self.done or self.finish_reason is not None

    def to_completion(self) -> Completion:
        """받은 것을 답으로 바꾼다. 글은 생각 글을 뗀 것이다."""
        return Completion(
            text=drop_thinking(self.thinking.raw),
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            finish_reason=self.finish_reason,
            truncated=self.finish_reason == LENGTH_FINISH,
        )


def pass_on(on_text: TextSink, text: str) -> None:
    """새 글이 있으면 넘긴다. 빈 글은 넘기지 않는다."""
    if text:
        on_text(text)


async def read_stream(lines: AsyncIterator[str], model: str, on_text: TextSink) -> Completion:
    """
    흘러오는 줄들을 끝까지 읽어 답을 만든다. 새 글은 오는 대로 on_text 에 넘긴다.

    [DONE] 을 보면 그만 읽는다. 끝까지 받지 못하고 줄이 끝나면 ProviderError('interrupted').
    붙잡아 둔 글은 끝까지 받은 것을 확인한 뒤에 넘긴다.
    """
    state = StreamState(model)
    async for line in lines:
        data = data_of(line)
        if data is None:
            continue
        if data == DONE:
            state.done = True
            break
        pass_on(on_text, state.add(parse_chunk(data)))
    if not state.is_complete():
        raise ProviderError('interrupted')
    pass_on(on_text, state.thinking.finish())
    return state.to_completion()
