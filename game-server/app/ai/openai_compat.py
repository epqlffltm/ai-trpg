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

실패는 모두 ProviderError 다. 응답의 본문은 오류에 싣지 않는다. 본문에 프롬프트(GM 메모 포함)가 되돌아와 있을 수 있다.
"""

import re
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx

from app.ai.provider import ChatMessage, Completion, GenerationParams, ProviderError, Reasoning

# 추론을 켰을 때 생각에 더 주는 토큰. 답에 쓰는 상한(max_tokens)은 그대로 두고 이만큼을 더한다
THINKING_TOKENS = {Reasoning.LOW: 1024, Reasoning.MEDIUM: 4096, Reasoning.HIGH: 8192}

# OpenAI 모양에서 "길이 상한에 걸려 멈췄다"는 뜻의 멈춘 이유
LENGTH_FINISH = 'length'

# content 에 섞여 온 생각 글. 닫힌 것, 그리고 닫히지 않은 채 끝까지 간 것
THINKING_PATTERN = re.compile(r'<think>.*?(?:</think>|$)', re.DOTALL)


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
    """보낼 요청의 본문. 추론을 아는 모델에는 추론 수준을 늘 싣는다. 끌 때도 'none' 을 보내야 꺼진다."""
    body: dict[str, Any] = {
        'model': model,
        'messages': [to_wire(message) for message in messages],
        'max_tokens': token_limit(params, supports_reasoning),
        'temperature': params.temperature,
        'stream': False,
    }
    if supports_reasoning:
        body['reasoning_effort'] = params.reasoning.value
    return body


async def post_chat(client: httpx.AsyncClient, url: str, body: dict[str, Any], timeout: float) -> Any:
    """요청을 보내고 받은 JSON 을 돌려준다. 연결, 시간 초과, 상태 코드, 형식의 실패는 ProviderError 다."""
    try:
        response = await client.post(url, json=body, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise ProviderError('timeout') from exc
    except httpx.HTTPError as exc:
        raise ProviderError('unreachable') from exc
    if response.status_code != httpx.codes.OK:
        raise ProviderError(f'status_{response.status_code}')
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError('not_json') from exc


def drop_thinking(text: str) -> str:
    """content 에 섞여 온 생각 글을 떼어 낸다. 닫히지 않은 생각 글은 끝까지가 생각이다."""
    return THINKING_PATTERN.sub('', text)


def read_completion(data: Any, model: str) -> Completion:
    """
    받은 JSON 에서 답을 꺼낸다. 모양이 다르면 ProviderError 다.

    생각 글(reasoning 칸)은 읽지 않는다. 답이 비어 있으면 빈 글로 돌려준다. 받을지는 쓰는 쪽이 정한다.
    """
    try:
        choice = data['choices'][0]
        content = choice['message'].get('content') or ''
        finish = choice.get('finish_reason')
        usage = data.get('usage') or {}
        input_tokens = usage.get('prompt_tokens')
        output_tokens = usage.get('completion_tokens')
        answered_by = data.get('model') or model
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ProviderError('malformed') from exc
    if not isinstance(content, str):
        raise ProviderError('malformed')
    return Completion(
        text=drop_thinking(content),
        model=answered_by,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        finish_reason=finish,
        truncated=finish == LENGTH_FINISH,
    )


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

    async def complete(self, messages: list[ChatMessage], params: GenerationParams) -> Completion:
        """메시지들을 보내고 모델이 만든 글을 받는다. 실패하면 ProviderError."""
        body = build_body(self.model, messages, params, self.supports_reasoning)
        data = await post_chat(self.client, chat_url(self.base_url), body, self.timeout)
        return read_completion(data, self.model)
