# game-server/app/ai/gemini.py

"""
Gemini 를 부르는 provider. Google 의 Gemini API(generateContent, 흘려 받기)를 SDK 없이 httpx 로 부른다.

generateContent 를 쓰고 Interactions API 는 쓰지 않는다.
  - Google 은 새 일에는 Interactions 를 권하지만 generateContent 도 "계속 온전히 지원"한다고 적었다(2026-10).
  - Interactions 는 대화를 Google 쪽에 저장하는 것이 기본(store=true)이다. 우리는 장면과 GM 메모를 맡기고 싶지 않다.
  - generateContent 는 한 번에 하나를 묻는다. 토큰 수(캐시, 생각)를 칸마다 따로 알려 준다.
  그래도 저장하지 말라고 store 를 false 로 싣는다.

다른 provider 와 다른 점.
  - 주소: {base}/v1beta/models/{모델}:streamGenerateContent?alt=sse. 머리: x-goog-api-key.
    키를 주소(?key=)에 싣지 않는다. 주소는 로그에 남을 수 있다.
  - 시스템 지시는 systemInstruction 칸이다. 대화는 contents 이고 역할은 user 와 model 이다(assistant 가 아니다).
  - 출력 상한(maxOutputTokens)에는 생각의 토큰도 들어간다.
  - 생각을 켜고 끄는 법이 모델마다 다르다. 모델 목록의 reasoning_style 을 보고 정한다(app/catalog/models.py).
      level_minimal 끌 수 없다. 끄라고 하면 thinkingLevel minimal. 켜면 low/medium/high
      level_low     끌 수 없다(minimal 도 받지 않는다). 끄라고 하면 low. 켜면 low/medium/high
      budget        끄기 thinkingBudget 0. 켜면 그 깊이의 토큰 수(2.5 Flash·Flash-Lite)
      budget_min    끌 수 없다. 끄라고 하면 가장 작은 128. 켜면 그 깊이의 토큰 수(2.5 Pro)
    생각할 때는 그 몫을 출력 상한에 더한다(app/ai/thinking.py). 생각의 요약은 달라고 하지 않는다(includeThoughts 없음).
  - 온도: Gemini 3 부터는 기본값(1.0)을 바꾸지 말라고 권한다. 받는 모델에만 싣는다(supports_temperature).
보내고 받는 HTTP 의 일(시간의 상한, 실패의 이름, Retry-After)은 app/ai/http_stream.py 가 한다.
"""

from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx
from pydantic import SecretStr

from app.ai.gemini_stream import read_gemini_stream
from app.ai.http_stream import stream_completion
from app.ai.openai_compat import THINKING_TOKENS
from app.ai.provider import ChatMessage, Completion, GenerationParams, Reasoning, Role, TextSink, ignore_text
from app.ai.thinking import thinking_budget
from app.catalog.models import ReasoningStyle

# 대화의 역할을 Gemini 의 이름으로. 어시스턴트는 model 이다
ROLES = {Role.USER: 'user', Role.ASSISTANT: 'model'}
# 생각을 끌 수 없는 깊이 방식에서 끄라고 할 때 주는 깊이
LOWEST_LEVEL = {ReasoningStyle.LEVEL_MINIMAL: 'minimal', ReasoningStyle.LEVEL_LOW: 'low'}
# 토큰 수 방식에서 끄라고 할 때 주는 생각의 토큰 수. budget_min(2.5 Pro)은 128 보다 작게 줄 수 없다
LOWEST_BUDGET = {ReasoningStyle.BUDGET: 0, ReasoningStyle.BUDGET_MIN: 128}


def stream_url(base_url: str, model: str) -> str:
    """흘려 받는 주소. 설정한 주소의 끝에 / 가 있든 없든 같다."""
    return f'{base_url.rstrip("/")}/v1beta/models/{model}:streamGenerateContent?alt=sse'


def system_of(messages: list[ChatMessage]) -> str:
    """시스템 메시지들을 이어 붙인 것. 없으면 빈 글."""
    return '\n\n'.join(message.content for message in messages if message.role == Role.SYSTEM)


def contents_of(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """시스템이 아닌 메시지들을 보내는 모양으로. 차례는 그대로다."""
    return [
        {'role': ROLES[message.role], 'parts': [{'text': message.content}]}
        for message in messages
        if message.role != Role.SYSTEM
    ]


def thinking_config(style: ReasoningStyle, reasoning: Reasoning) -> dict[str, Any]:
    """생각을 켜고 끄는 칸(thinkingConfig). 깊이 방식은 thinkingLevel, 토큰 수 방식은 thinkingBudget 이다."""
    if style in LOWEST_LEVEL:
        level = LOWEST_LEVEL[style] if reasoning == Reasoning.NONE else reasoning.value
        return {'thinkingLevel': level}
    if style in LOWEST_BUDGET:
        budget = LOWEST_BUDGET[style] if reasoning == Reasoning.NONE else THINKING_TOKENS[reasoning]
        return {'thinkingBudget': budget}
    raise ValueError(f'Gemini 가 받지 않는 생각의 방식이다: {style}')


def generation_config(params: GenerationParams, style: ReasoningStyle, supports_temperature: bool) -> dict[str, Any]:
    """생성 설정. 출력 상한에는 생각의 몫을 더한다. 온도는 받는 모델에만."""
    config: dict[str, Any] = {
        'maxOutputTokens': params.max_tokens + thinking_budget(style, params.reasoning),
        'thinkingConfig': thinking_config(style, params.reasoning),
    }
    if supports_temperature:
        config['temperature'] = params.temperature
    return config


def build_body(
    messages: list[ChatMessage], params: GenerationParams, style: ReasoningStyle, supports_temperature: bool
) -> dict[str, Any]:
    """보낼 요청의 본문. 저장하지 말라고 한다(store false)."""
    body: dict[str, Any] = {
        'contents': contents_of(messages),
        'generationConfig': generation_config(params, style, supports_temperature),
        'store': False,
    }
    system = system_of(messages)
    if system:
        body['systemInstruction'] = {'parts': [{'text': system}]}
    return body


def gemini_headers(api_key: SecretStr | None) -> dict[str, str]:
    """키를 담은 머리. 키가 없으면 빈 것."""
    if api_key is None or not api_key.get_secret_value():
        return {}
    return {'x-goog-api-key': api_key.get_secret_value()}


@dataclass(frozen=True)
class GeminiProvider:
    """
    Gemini 를 부르는 provider. 고르는 것(app/ai/routing.py)이 모델 목록의 값으로 만든다.

    client 는 앱이 들고 있는 httpx 클라이언트다. 닫는 것은 앱이 한다.
    base_url 은 /v1beta 앞까지다(https://generativelanguage.googleapis.com). api_key 는 repr 에 나오지 않는다.
    """

    client: httpx.AsyncClient
    base_url: str
    model: str
    api_key: SecretStr | None
    reasoning_style: ReasoningStyle
    supports_temperature: bool = False
    timeout: float = 120.0
    kind: str = 'gemini'

    async def complete(
        self, messages: list[ChatMessage], params: GenerationParams, on_text: TextSink = ignore_text
    ) -> Completion:
        """
        메시지들을 보내고 모델이 쓴 글을 흘려 받는다. 새 글은 오는 대로 on_text 에 넘긴다. 실패하면 ProviderError.

        호출 전체가 timeout 초를 넘으면 끊는다. 조각이 계속 와도 끊는다.
        """
        body = build_body(messages, params, self.reasoning_style, self.supports_temperature)
        read = partial(read_gemini_stream, model=self.model, on_text=on_text)
        url = stream_url(self.base_url, self.model)
        return await stream_completion(self.client, url, body, gemini_headers(self.api_key), self.timeout, read)
