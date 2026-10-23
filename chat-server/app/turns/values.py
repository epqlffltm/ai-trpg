# chat-server/app/turns/values.py

"""
말 한 번이 들고 다니는 값들. ORM 객체가 아니라서 세션이 닫힌 뒤에도, 따로 도는 작업에서도 읽는다.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from ai_core.provider import ChatMessage

from app.turns.models import Outcome


@dataclass(frozen=True)
class SavedMessage:
    """저장한 말. 응답에 싣는 값이다(대화 읽기의 말과 같은 칸)."""

    id: uuid.UUID
    parent_id: uuid.UUID | None
    role: str
    content: str
    status: str
    created_at: datetime
    suggestions: tuple[str, ...] = ()
    event_scene: str | None = None
    # 모델이 고른 표정(캐릭터 그림의 표정 이름). 기본 표정이면 None
    expression: str | None = None


@dataclass(frozen=True)
class PromptOptions:
    """모델에 보낼 메시지를 만드는 설정. 설정(Settings)에서 온다."""

    # 지난 말의 양의 상한(글자). 최근 말부터 채운다
    context_chars: int
    # 다음 답 추천을 받는가. 끄면 카드에 지시를 넣지 않는다
    suggestions: bool


@dataclass(frozen=True)
class TurnStart:
    """begin_turn 이 만든 말 한 번. 그 뒤의 일은 이것만 들고 간다."""

    conversation_id: uuid.UUID
    generation_id: uuid.UUID
    owner_id: uuid.UUID
    model_slug: str
    reference: str
    price_code: str
    user_message: SavedMessage
    messages: list[ChatMessage]
    # 이어서 출력이면 이어 쓰는 끊긴 답. 새 글은 이 말의 끝에 붙는다. 보통의 말 한 번이면 None
    continued: SavedMessage | None = None
    # 행동에 한마디를 덧붙였으면 그 행동 말. user_message 는 한마디이고 이 말 아래에 있다. 아니면 None
    action: SavedMessage | None = None
    # 모델이 고를 수 있는 표정과 그 캐릭터 그림(app/world/sprites.py 의 expression_images). 비어 있으면 고르지 않는다
    expressions: Mapping[str, uuid.UUID] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnResult:
    """
    모델을 부른 결과. text 가 비어 있으면 저장할 답이 없다. text 는 본문이고, 선택지는 suggestions 에 따로 있다.
    이어서 출력이면 text 는 끊긴 답 끝에 붙일 글이다(되풀이한 앞부분을 뗐다).
    """

    text: str
    outcome: Outcome
    error_code: str | None = None
    suggestions: tuple[str, ...] = ()
    # 모델이 고른 표정. 기본이거나 고르지 않았으면 None
    expression: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None
