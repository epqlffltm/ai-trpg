# shared/ai-core/src/ai_core/openai_compat.py

"""
OpenAI 와 같은 모양의 주소(/chat/completions)를 부르는 provider.

Ollama, LM Studio, vLLM, 그리고 같은 모양을 받는 클라우드 API(OpenAI, Z.ai, DeepInfra)를 이 하나로 부른다.
주소, 모델 이름, 키, 모델이 받는 칸만 다르다. 어느 모델을 어떤 값으로 부를지는 ai_core/routing.py 가 정한다.
SDK 를 쓰지 않고 httpx 로 직접 부른다. 쓰는 칸이 몇 개 안 되고, 앱이 이미 httpx 클라이언트를 하나 들고 있다.

키(api_key)가 있으면 Authorization 머리에 싣는다. 서버 곁의 모델(Ollama)은 키가 없다.
키는 오류, 로그, 기록 어디에도 싣지 않는다. 비밀값(SecretStr)으로 들고 다니다 머리를 만들 때만 꺼낸다.

모델마다 받는 칸이 다르다(app/catalog/models.py).
  - 출력 상한: 서버 곁의 모델과 옛 모델은 max_tokens 를 받는다.
    OpenAI 의 생각하는 모델은 max_completion_tokens 만 받는다(token_field).
  - 온도: 받지 않는 모델에는 싣지 않는다(supports_temperature). 실으면 400 이 난다.

추론(생각 모드):
  추론하는 모델은 답하기 전에 속으로 따져 보는 글을 쓴다. Ollama 는 그 글을 content 가 아니라 reasoning 칸에 담는다.
  추론은 토큰을 먹는다. 끄지 않으면 생각만 하다가 길이 상한에 닿아 답(content)이 비어 오기도 한다.
  그래서 추론 수준(reasoning_effort)을 늘 보낸다. 끌 때는 'none' 이다. 켤 때는 생각에 쓸 토큰을 상한에 더한다.
  추론을 모르는 모델이면(supports_reasoning=False) 보내지 않는다.
  생각을 다른 칸으로 켜고 끄는 창구도 있다(Z.ai 의 thinking: {"type": "disabled"}). 그런 모델은 thinking_switch 다.
  끌 수 없는 모델(always_thinks)에는 끄라는 칸(none, disabled)을 보내지 않는다.
  끄라고 해도 가장 낮은 깊이의 몫을 상한에 더한다.
  그 모델이 추론 수준을 알면(supports_reasoning) 끄라고 할 때 가장 낮은 수준(low)을 보낸다. 보내지 않으면 모델의 기본값
  (OpenAI 는 medium, GLM-5.3 은 max)으로 생각해 더한 몫을 넘고 장면이 잘린다.
  생각이 장면의 몫을 먹어 장면이 잘리지 않게 한다(ai_core/thinking.py 와 같은 규칙).
  content 에 생각 글(<think>...</think>)이 섞여 오면 떼어 낸다. 실행기나 모델에 따라 그렇게 오는 경우가 있다.

답은 늘 흘려 받는다(stream). 쓰는 대로 조각을 받아 앉은 사람에게 미리 보여 줄 수 있다(ai_core/streaming.py).
흘려 받지 않는 길을 따로 두지 않는다. Ollama, LM Studio, vLLM, OpenAI 가 모두 흘려 보낸다. 길이 둘이면 검증도 둘이다.

보내고 받는 HTTP 의 일(시간의 상한, 실패의 이름, Retry-After)은 ai_core/http_stream.py 가 한다.
Claude 의 provider 와 같다.
흘러온 줄을 읽는 것은 ai_core/streaming.py 다. 도중의 오류 조각은 stream_error, 모양이 다르면 malformed 다.
"""

from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx
from pydantic import SecretStr

from ai_core.http_stream import bearer_headers, stream_completion
from ai_core.provider import (
    ChatMessage,
    Completion,
    GenerationParams,
    Reasoning,
    TextSink,
    ignore_text,
)
from ai_core.streaming import read_stream

# 추론을 켰을 때 생각에 더 주는 토큰. 답에 쓰는 상한(max_tokens)은 그대로 두고 이만큼을 더한다
THINKING_TOKENS = {Reasoning.LOW: 1024, Reasoning.MEDIUM: 4096, Reasoning.HIGH: 8192}
# 출력 상한을 담는 칸의 기본 이름. 서버 곁의 모델이 받는 것이다
DEFAULT_TOKEN_FIELD = 'max_tokens'


@dataclass(frozen=True)
class WireOptions:
    """모델이 받는 칸. 보낼 본문을 만들 때 본다. 기본값은 서버 곁의 모델(Ollama)에 맞다."""

    # 추론 수준(reasoning_effort)을 아는가
    supports_reasoning: bool = True
    # 온도를 받는가
    supports_temperature: bool = True
    # 출력 상한을 담는 칸의 이름(max_tokens, max_completion_tokens)
    token_field: str = DEFAULT_TOKEN_FIELD
    # 생각을 thinking 칸({"type": "enabled" | "disabled"})으로 켜고 끄는가(Z.ai).
    # 그러면 reasoning_effort 는 보내지 않는다
    thinking_switch: bool = False
    # 생각을 끌 수 없는가. 끄라고 해도 생각한다
    always_thinks: bool = False


# 따로 정하지 않았을 때 받는 칸. 서버 곁의 모델이다
LOCAL_OPTIONS = WireOptions()


def chat_url(base_url: str) -> str:
    """대화를 부르는 주소. 설정한 주소의 끝에 / 가 있든 없든 같다."""
    return f'{base_url.rstrip("/")}/chat/completions'


def to_wire(message: ChatMessage) -> dict[str, str]:
    """메시지 하나를 보내는 모양으로 바꾼다."""
    return {'role': message.role.value, 'content': message.content}


def thinking_tokens(params: GenerationParams, options: WireOptions) -> int:
    """
    생각에 더 주는 토큰. 생각하지 않으면 0.

    생각을 켤 수 있는 모델에 켜라고 했으면 그 깊이의 몫이다. 끌 수 없는 모델에 끄라고 했으면 가장 낮은 깊이의 몫이다.
    """
    if params.reasoning != Reasoning.NONE and (options.supports_reasoning or options.thinking_switch):
        return THINKING_TOKENS[params.reasoning]
    if options.always_thinks:
        return THINKING_TOKENS[Reasoning.LOW]
    return 0


def token_limit(params: GenerationParams, options: WireOptions) -> int:
    """보낼 토큰 상한. 생각하면 생각에 쓸 몫을 더한다. 생각이 답의 몫까지 먹지 않게 한다."""
    return params.max_tokens + thinking_tokens(params, options)


def lowest_effort(params: GenerationParams) -> Reasoning:
    """끌 수 없는 모델에 보내는 추론 수준. 끄라고 했으면 가장 낮은 low, 아니면 그대로다."""
    return Reasoning.LOW if params.reasoning == Reasoning.NONE else params.reasoning


def thinking_switch(params: GenerationParams) -> dict[str, str]:
    """thinking 칸. 끄라고 했으면 disabled, 아니면 enabled 다."""
    return {'type': 'disabled' if params.reasoning == Reasoning.NONE else 'enabled'}


def build_body(
    model: str, messages: list[ChatMessage], params: GenerationParams, options: WireOptions = LOCAL_OPTIONS
) -> dict[str, Any]:
    """
    보낼 요청의 본문. 추론을 아는 모델에는 추론 수준을 늘 싣는다. 끌 때도 'none' 을 보내야 꺼진다.
    thinking 칸으로 켜고 끄는 모델에는 그 칸을 늘 싣는다. 끌 수 없는 모델에는 끄는 칸을 싣지 않는다
    (추론 수준을 알면 low 부터 싣는다).

    출력 상한은 모델이 받는 칸에 싣는다. 온도는 받는 모델에만 싣는다.
    흘려 받는다. 토큰 수는 흘려 받을 때 따로 달라고 해야 온다(include_usage).
    """
    body: dict[str, Any] = {
        'model': model,
        'messages': [to_wire(message) for message in messages],
        options.token_field: token_limit(params, options),
        'stream': True,
        'stream_options': {'include_usage': True},
    }
    if options.supports_temperature:
        body['temperature'] = params.temperature
    if options.always_thinks:
        if options.supports_reasoning:
            body['reasoning_effort'] = lowest_effort(params).value
        return body
    if options.thinking_switch:
        body['thinking'] = thinking_switch(params)
    elif options.supports_reasoning:
        body['reasoning_effort'] = params.reasoning.value
    return body


@dataclass(frozen=True)
class OpenAICompatProvider:
    """
    OpenAI 와 같은 모양의 주소를 부르는 provider.

    client 는 앱이 들고 있는 httpx 클라이언트다. 닫는 것은 앱이 한다.
    base_url 은 /chat/completions 앞까지다(Ollama 면 http://127.0.0.1:11434/v1, OpenAI 면 https://api.openai.com/v1).
    kind 는 호출의 기록에 적는 창구의 이름이다. 서버 곁의 모델이면 openai_compat, OpenAI 면 openai, Z.ai 면 zai,
    DeepInfra 면 deepinfra 다.
    api_key 는 repr 에 나오지 않는다(SecretStr).
    """

    client: httpx.AsyncClient
    base_url: str
    model: str
    timeout: float = 120.0
    options: WireOptions = LOCAL_OPTIONS
    api_key: SecretStr | None = None
    kind: str = 'openai_compat'

    @property
    def supports_reasoning(self) -> bool:
        """추론 수준을 아는 모델인가."""
        return self.options.supports_reasoning

    async def complete(
        self, messages: list[ChatMessage], params: GenerationParams, on_text: TextSink = ignore_text
    ) -> Completion:
        """
        메시지들을 보내고 모델이 만든 글을 흘려 받는다. 새 글은 오는 대로 on_text 에 넘긴다. 실패하면 ProviderError.

        호출 전체가 timeout 초를 넘으면 끊는다. 조각이 계속 와도 끊는다.
        """
        body = build_body(self.model, messages, params, self.options)
        read = partial(read_stream, model=self.model, on_text=on_text)
        url = chat_url(self.base_url)
        return await stream_completion(self.client, url, body, bearer_headers(self.api_key), self.timeout, read)
