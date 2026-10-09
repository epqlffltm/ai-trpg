# game-server/app/ai/provider.py

"""
언어 모델(LLM)을 부르는 것(provider)의 모양.

게임 서버의 다른 코드는 이 모양만 안다. 어느 회사의 모델인지, 로컬에서 도는지 클라우드에서 도는지 모른다.
모델을 바꿀 때는 이 모양을 따르는 구현을 바꿔 끼운다(로컬 Ollama → 클라우드 API).

어느 회사의 SDK 타입도 쓰지 않는다. 메시지, 생성 설정, 결과의 모양을 여기에 따로 둔다.
SDK 가 바뀌거나 회사를 옮겨도, 이 파일 밖의 코드는 바뀌지 않는다.

메시지는 역할이 붙은 목록이다(대화형). 요즘의 모델과 API(OpenAI, Anthropic, Ollama, vLLM)가 모두 이 모양을 받는다.
시스템 지시를 따로 두어야 지시가 플레이어의 글에 묻히지 않는다.
"""

import enum
from dataclasses import dataclass
from typing import Protocol


class Role(enum.StrEnum):
    """메시지를 누가 말했는가."""

    # 모델에게 주는 지시. 맨 앞에 하나 둔다
    SYSTEM = 'system'
    # 사람 쪽의 말. 여기서는 플레이어들의 선언과 판정의 결과다
    USER = 'user'
    # 모델 쪽의 말. 여기서는 GM 의 지난 서술이다
    ASSISTANT = 'assistant'


class Reasoning(enum.StrEnum):
    """
    모델이 답하기 전에 속으로 따져 보는 정도(추론, 생각 모드).

    추론은 토큰과 시간을 먹는다. 서술은 기본으로 끈다. 추리처럼 앞뒤를 맞춰야 하는 이야기에서는 켤 수 있다.
    추론을 모르는 모델이면 provider 가 이 값을 보내지 않는다.
    """

    NONE = 'none'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


@dataclass(frozen=True)
class ChatMessage:
    """메시지 하나."""

    role: Role
    content: str


@dataclass(frozen=True)
class GenerationParams:
    """
    글을 만들 때의 설정.

    max_tokens: 답의 길이의 상한(토큰). 비용과 시간의 상한이기도 하다. 추론에 쓰는 토큰은 provider 가 따로 더한다.
    temperature: 0 에 가까울수록 같은 입력에 비슷한 글이, 클수록 다양한 글이 나온다.
    reasoning: 추론의 정도. 호출마다 정한다. 기본은 끔이다.
    """

    max_tokens: int
    temperature: float
    reasoning: Reasoning = Reasoning.NONE


@dataclass(frozen=True)
class Completion:
    """
    모델이 만든 글과, 그것을 만든 사정.

    토큰 수는 provider 가 알려 주면 채운다. 알려 주지 않는 provider 도 있어서 비어 있을 수 있다.
    finish_reason 은 왜 멈췄는가다(다 썼다, 길이 상한에 닿았다 등). 이름은 provider 마다 다르다.
    truncated 는 길이 상한에 걸려 중간에 끊겼다는 뜻이다. provider 가 자기의 finish_reason 을 이 뜻으로 바꿔 둔다.
    쓰는 쪽은 provider 마다 다른 이름을 몰라도 된다.
    """

    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    truncated: bool = False


class ProviderError(Exception):
    """모델을 부르는 데 실패했다. 연결이 안 되거나, 시간이 넘었거나, 이상한 답이 왔다."""


class LLMProvider(Protocol):
    """모델을 부르는 것의 모양. 이 메서드가 있으면 provider 다."""

    async def complete(self, messages: list[ChatMessage], params: GenerationParams) -> Completion:
        """메시지들을 보내고 모델이 만든 글을 받는다. 실패하면 ProviderError."""
        ...
