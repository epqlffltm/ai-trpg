# chat-server/app/turns/values.py

"""
말 한 번이 들고 다니는 값들. ORM 객체가 아니라서 세션이 닫힌 뒤에도, 따로 도는 작업에서도 읽는다.
"""

import uuid
from dataclasses import dataclass
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


@dataclass(frozen=True)
class TurnResult:
    """모델을 부른 결과. text 가 비어 있으면 저장할 답이 없다."""

    text: str
    outcome: Outcome
    error_code: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None
