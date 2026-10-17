# game-server/app/ai/anthropic.py

"""
Claude 를 부르는 provider. Anthropic 의 Messages API(/v1/messages)를 SDK 없이 httpx 로 부른다.

OpenAI 모양의 provider(app/ai/openai_compat.py)와 다른 점.
  - 시스템 지시는 메시지 목록이 아니라 맨 위의 system 칸이다. 시스템 메시지들을 이어 붙여 거기 싣는다.
  - 머리: Authorization: Bearer <키>, anthropic-version. 키는 비밀값(SecretStr)이다. 오류, 로그, 기록에 싣지 않는다.
  - 생각(thinking)을 켜고 끄는 법이 모델마다 다르다. 모델 목록의 reasoning_style 을 보고 정한다(app/catalog/models.py).
      adaptive      끄기 {"type": "disabled"}       켜기 {"type": "adaptive"} + effort
      always        끌 수 없다. effort low 로 주고 출력 상한에 생각의 몫을 더한다
      between_tools 끄기 {"type": "between_tools"}  켜기 adaptive + effort
      budget        끄기 {"type": "disabled"}       켜기 {"type": "enabled", "budget_tokens": …}
    생각한 글은 돌려받지 않게 한다(display: omitted). 받아도 읽지 않는다(app/ai/anthropic_stream.py).
    생각을 하면 출력 상한(max_tokens)에 생각의 토큰도 들어간다. 그래서 생각할 때는 생각의 몫을 상한에 더한다.
    생각의 토큰은 글을 돌려받지 않아도 출력으로 값이 매겨진다.
  - 온도: 5 세대와 Opus 4.7·4.8 은 기본값이 아닌 온도에 400 을 낸다. 받는 모델에만 싣는다(supports_temperature).
보내고 받는 HTTP 의 일(시간의 상한, 실패의 이름, Retry-After)은 app/ai/http_stream.py 가 한다. 과부하는 status_529 다.
"""

from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx
from pydantic import SecretStr

from app.ai.anthropic_stream import read_claude_stream
from app.ai.http_stream import bearer_headers, stream_completion
from app.ai.openai_compat import THINKING_TOKENS
from app.ai.provider import ChatMessage, Completion, GenerationParams, Reasoning, Role, TextSink, ignore_text
from app.ai.thinking import LOWEST_EFFORT, thinking_budget
from app.catalog.models import ReasoningStyle

# 머리에 싣는 API 의 판
ANTHROPIC_VERSION = '2023-06-01'


def messages_url(base_url: str) -> str:
    """대화를 부르는 주소. 설정한 주소의 끝에 / 가 있든 없든 같다."""
    return f'{base_url.rstrip("/")}/v1/messages'


def system_of(messages: list[ChatMessage]) -> str:
    """시스템 메시지들을 이어 붙인 것. 없으면 빈 글."""
    return '\n\n'.join(message.content for message in messages if message.role == Role.SYSTEM)


def turns_of(messages: list[ChatMessage]) -> list[dict[str, str]]:
    """시스템이 아닌 메시지들을 보내는 모양으로. 차례는 그대로다."""
    return [
        {'role': message.role.value, 'content': message.content} for message in messages if message.role != Role.SYSTEM
    ]


def thinking_off(style: ReasoningStyle) -> dict[str, Any]:
    """생각을 끄는 thinking 칸과 그에 딸린 칸. 끌 수 없는 모델이면 가장 낮은 깊이로 생각하게 한다."""
    if style == ReasoningStyle.BETWEEN_TOOLS:
        return {'thinking': {'type': 'between_tools'}}
    if style == ReasoningStyle.ALWAYS:
        return thinking_on(style, LOWEST_EFFORT)
    return {'thinking': {'type': 'disabled'}}


def thinking_on(style: ReasoningStyle, reasoning: Reasoning) -> dict[str, Any]:
    """생각을 켜는 thinking 칸과 그에 딸린 칸. 4.5 세대는 토큰 상한으로, 나머지는 깊이(effort)로 준다."""
    if style == ReasoningStyle.BUDGET:
        return {'thinking': {'type': 'enabled', 'budget_tokens': THINKING_TOKENS[reasoning]}}
    return {'thinking': {'type': 'adaptive', 'display': 'omitted'}, 'output_config': {'effort': reasoning.value}}


def thinking_fields(style: ReasoningStyle, reasoning: Reasoning) -> dict[str, Any]:
    """생각을 켜고 끄는 칸들. 생성 설정의 깊이와 모델의 방식으로 정한다."""
    if reasoning == Reasoning.NONE:
        return thinking_off(style)
    return thinking_on(style, reasoning)


def build_body(
    model: str,
    messages: list[ChatMessage],
    params: GenerationParams,
    style: ReasoningStyle,
    supports_temperature: bool,
) -> dict[str, Any]:
    """보낼 요청의 본문. 흘려 받는다. 출력 상한에는 생각의 몫을 더한다."""
    body: dict[str, Any] = {
        'model': model,
        'max_tokens': params.max_tokens + thinking_budget(style, params.reasoning),
        'messages': turns_of(messages),
        'stream': True,
        **thinking_fields(style, params.reasoning),
    }
    system = system_of(messages)
    if system:
        body['system'] = system
    if supports_temperature:
        body['temperature'] = params.temperature
    return body


def claude_headers(api_key: SecretStr | None) -> dict[str, str]:
    """키와 API 의 판을 담은 머리."""
    return {**bearer_headers(api_key), 'anthropic-version': ANTHROPIC_VERSION}


@dataclass(frozen=True)
class AnthropicProvider:
    """
    Claude 를 부르는 provider. 고르는 것(app/ai/routing.py)이 모델 목록의 값으로 만든다.

    client 는 앱이 들고 있는 httpx 클라이언트다. 닫는 것은 앱이 한다.
    base_url 은 /v1/messages 앞까지다(https://api.anthropic.com). api_key 는 repr 에 나오지 않는다.
    """

    client: httpx.AsyncClient
    base_url: str
    model: str
    api_key: SecretStr | None
    reasoning_style: ReasoningStyle
    supports_temperature: bool = False
    timeout: float = 120.0
    kind: str = 'anthropic'

    async def complete(
        self, messages: list[ChatMessage], params: GenerationParams, on_text: TextSink = ignore_text
    ) -> Completion:
        """
        메시지들을 보내고 모델이 쓴 글을 흘려 받는다. 새 글은 오는 대로 on_text 에 넘긴다. 실패하면 ProviderError.

        호출 전체가 timeout 초를 넘으면 끊는다. 조각이 계속 와도 끊는다.
        """
        body = build_body(self.model, messages, params, self.reasoning_style, self.supports_temperature)
        read = partial(read_claude_stream, model=self.model, on_text=on_text)
        url = messages_url(self.base_url)
        return await stream_completion(self.client, url, body, claude_headers(self.api_key), self.timeout, read)
