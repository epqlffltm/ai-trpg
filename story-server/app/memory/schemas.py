# story-server/app/memory/schemas.py

"""
기억 메모 API 의 입력과 응답의 모양(chat 과 같다).
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.memory.models import NOTE_MAX_CHARS, NoteSource

NoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NOTE_MAX_CHARS)]


class NoteWrite(BaseModel):
    """메모를 쓰거나 고칠 때 받는 글. 앞뒤 빈칸은 걷는다."""

    model_config = ConfigDict(extra='forbid')

    text: NoteText


class NoteOut(BaseModel):
    """
    메모 하나(chat 과 같은 모양). source 는 누가 썼는가(user, summary)다. pending 이면 요약의 제안이고 받아들이기 전이다
    (모델에 가지 않는다. 화면은 받아들이기와 버리기를 보인다). accepted_at 은 제안을 받아들인 시각이다.
    """

    id: uuid.UUID
    text: str
    source: NoteSource
    pending: bool
    accepted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SummaryOut(BaseModel):
    """지금 가지의 굴리는 요약(읽기만). covered_up_to 는 요약한 마지막 말의 id 다(첫 말부터 그 말까지를 요약했다)."""

    text: str
    covered_up_to: uuid.UUID
    created_at: datetime
