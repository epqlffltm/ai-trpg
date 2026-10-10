# game-server/app/ai/openai_compat.py

"""
OpenAI 와 같은 모양의 주소(/chat/completions)를 부르는 provider.

Ollama, LM Studio, vLLM, 그리고 같은 모양을 받는 클라우드 API 를 이 하나로 부른다. 주소와 모델 이름만 다르다.
SDK 를 쓰지 않고 httpx 로 직접 부른다. 쓰는 칸이 몇 개 안 되고, 앱이 이미 httpx 클라이언트를 하나 들고 있다.

추론(생각 모드):
  추론하는 모델은 답하기 전에 속으로 따져 보는 글을 쓴다. Ollama 는 그 글을 content 가 아니라 reasoning 칸에 담는다.
  추론은 토큰을 먹는다. 끄지 않으면 생각만 하다가 길이 상한에 닿아 답(content)이 비어 오기도 한다.
  그래서 추론 수준(reasoning_effort)을 늘 보낸다. 끌 때는 'none' 이다. 켤 때는 생각에 쓸 토큰을 상한에 더한다.
  추론을 모르는 모델이면(supports_reasoning=False) 보내지 않는다.
  content 에 생각 글(<think>...</think>)이 섞여 오면 떼어 낸다. 실행기나 모델에 따라 그렇게 오는 경우가 있다.

답은 늘 흘려 받는다(stream). 쓰는 대로 조각을 받아 앉은 사람에게 미리 보여 줄 수 있다(app/ai/streaming.py).
흘려 받지 않는 길을 따로 두지 않는다. Ollama, LM Studio, vLLM, OpenAI 가 모두 흘려 보낸다. 길이 둘이면 검증도 둘이다.

시간의 상한.
  httpx 의 timeout 은 "다음 바이트가 올 때까지"의 상한이다. 흘려 받으면 조각이 계속 오는 한 끝없이 길어질 수 있다.
  그래서 호출 전체에 따로 상한(timeout)을 건다. 다시 시도하는 쪽이 "한 번 부르는 데 이만큼"을 믿고 남은 시간을 센다.

실패는 모두 ProviderError 다. 응답의 본문은 오류에 싣지 않는다. 본문에 프롬프트(GM 메모 포함)가 되돌아와 있을 수 있다.
  - 연결이 안 됨: unreachable. 받는 도중에 끊김: interrupted. 둘을 나눈다. 서버가 꺼진 것과 한 번 끊긴 것은 다르다.
  - 시간 초과: timeout. 상태 코드: status_코드. 도중의 오류 조각: stream_error. 모양이 다름: malformed.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx

from app.ai.provider import (
    ChatMessage,
    Completion,
    GenerationParams,
    ProviderError,
    Reasoning,
    TextSink,
    ignore_text,
)
from app.ai.streaming import read_stream

# 추론을 켰을 때 생각에 더 주는 토큰. 답에 쓰는 상한(max_tokens)은 그대로 두고 이만큼을 더한다
THINKING_TOKENS = {Reasoning.LOW: 1024, Reasoning.MEDIUM: 4096, Reasoning.HIGH: 8192}


def chat_url(base_url: str) -> str:
    """대화를 부르는 주소. 설정한 주소의 끝에 / 가 있든 없든 같다."""
    return f'{base_url.rstrip("/")}/chat/completions'


def to_wire(message: ChatMessage) -> dict[str, str]:
    """메시지 하나를 보내는 모양으로 바꾼다."""
    return {'role': message.role.value, 'content': message.content}


def token_limit(params: GenerationParams, supports_reasoning: bool) -> int:
    """보낼 토큰 상한. 추론을 켜면 생각에 쓸 몫을 더한다. 생각이 답의 몫까지 먹지 않게 한다."""
    if not supports_reasoning or params.reasoning == Reasoning.NONE:
        return params.max_tokens
    return params.max_tokens + THINKING_TOKENS[params.reasoning]


def build_body(
    model: str, messages: list[ChatMessage], params: GenerationParams, supports_reasoning: bool
) -> dict[str, Any]:
    """
    보낼 요청의 본문. 추론을 아는 모델에는 추론 수준을 늘 싣는다. 끌 때도 'none' 을 보내야 꺼진다.

    흘려 받는다. 토큰 수는 흘려 받을 때 따로 달라고 해야 온다(include_usage).
    """
    body: dict[str, Any] = {
        'model': model,
        'messages': [to_wire(message) for message in messages],
        'max_tokens': token_limit(params, supports_reasoning),
        'temperature': params.temperature,
        'stream': True,
        'stream_options': {'include_usage': True},
    }
    if supports_reasoning:
        body['reasoning_effort'] = params.reasoning.value
    return body


async def lines_of(response: httpx.Response) -> AsyncIterator[str]:
    """받는 중인 응답의 줄들. 받는 도중의 시간 초과와 끊김을 ProviderError 로 바꾼다."""
    try:
        async for line in response.aiter_lines():
            yield line
    except httpx.TimeoutException as exc:
        raise ProviderError('timeout') from exc
    except httpx.HTTPError as exc:
        raise ProviderError('interrupted') from exc


async def stream_chat(
    client: httpx.AsyncClient, url: str, body: dict[str, Any], timeout: float, model: str, on_text: TextSink
) -> Completion:
    """
    요청을 보내고 흘러오는 답을 끝까지 읽는다.

    답이 오기 시작하기 전의 실패(연결, 시간 초과, 상태 코드)를 여기서 ProviderError 로 바꾼다.
    받는 도중의 실패는 lines_of 가 바꾼다.
    """
    try:
        async with client.stream('POST', url, json=body, timeout=timeout) as response:
            if response.status_code != httpx.codes.OK:
                raise ProviderError(f'status_{response.status_code}')
            return await read_stream(lines_of(response), model, on_text)
    except httpx.TimeoutException as exc:
        raise ProviderError('timeout') from exc
    except httpx.HTTPError as exc:
        raise ProviderError('unreachable') from exc


@dataclass(frozen=True)
class OpenAICompatProvider:
    """
    OpenAI 와 같은 모양의 주소를 부르는 provider.

    client 는 앱이 들고 있는 httpx 클라이언트다. 닫는 것은 앱이 한다.
    base_url 은 /chat/completions 앞까지다(Ollama 면 http://127.0.0.1:11434/v1).
    """

    kind: ClassVar[str] = 'openai_compat'

    client: httpx.AsyncClient
    base_url: str
    model: str
    timeout: float = 120.0
    supports_reasoning: bool = True

    async def complete(
        self, messages: list[ChatMessage], params: GenerationParams, on_text: TextSink = ignore_text
    ) -> Completion:
        """
        메시지들을 보내고 모델이 만든 글을 흘려 받는다. 새 글은 오는 대로 on_text 에 넘긴다. 실패하면 ProviderError.

        호출 전체가 timeout 초를 넘으면 끊는다. 조각이 계속 와도 끊는다.
        """
        body = build_body(self.model, messages, params, self.supports_reasoning)
        try:
            async with asyncio.timeout(self.timeout):
                return await stream_chat(self.client, chat_url(self.base_url), body, self.timeout, self.model, on_text)
        except TimeoutError as exc:
            raise ProviderError('timeout') from exc
