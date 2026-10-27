# story-server/app/turns/values.py

"""
말 한 번이 들고 다니는 값들. ORM 객체가 아니라서 세션이 닫힌 뒤에도, 따로 도는 작업에서도 읽는다.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from ai_core.provider import ChatMessage

from app.conversations.schemas import StateOut
from app.turns.models import Outcome
from app.turns.segments import Segment


@dataclass(frozen=True)
class SavedMessage:
    """저장한 말. 응답에 싣는 값이다(세션 읽기의 말과 같은 칸)."""

    id: uuid.UUID
    parent_id: uuid.UUID | None
    role: str
    content: str
    status: str
    created_at: datetime
    segments: tuple[dict, ...] = ()
    cast: tuple[str, ...] = ()
    event_id: str | None = None
    ending_id: str | None = None
    suggestions: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptOptions:
    """모델에 보낼 메시지를 만드는 설정. 설정(Settings)에서 온다."""

    # 지난 말의 양의 상한(글자). 최근 말부터 채운다
    context_chars: int
    # 다음 답 추천. 켜면 답 끝에 선택지 셋을 함께 받는다(conversation_core/suggestions.py)
    suggestions: bool = False


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
    # 장면의 인물(인물의 id). 답의 말하는 사람은 이 안에서만 받는다(app/turns/segments.py)
    cast: tuple[str, ...] = ()
    # 표식의 이름 → 인물의 id(app/turns/segments.py 의 speaker_labels)
    labels: Mapping[str, str] = field(default_factory=dict)
    # 인물의 id → 고를 수 있는 표정의 이름들(app/turns/segments.py). 표정이 없는 인물은 없다
    expressions: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # 사람의 말이나 행동 뒤의 상태(응답의 모양). turn 메시지에 싣는다
    state: StateOut | None = None
    # 이어서 출력이면 이어 쓰는 끊긴 답. 새 조각은 그 답에 붙는다(app/turns/service.py 의 extension_of)
    continued: SavedMessage | None = None


@dataclass(frozen=True)
class TurnResult:
    """
    모델을 부른 결과. segments 가 비어 있으면 저장할 답이 없다.
    dropped 는 장면에 없는 인물의 줄을 버린 수다. suggestions 는 다 쓴 답의 다음 답 추천이다.
    """

    segments: tuple[Segment, ...]
    outcome: Outcome
    suggestions: tuple[str, ...] = ()
    error_code: str | None = None
    dropped: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None
