# chat-server/app/memory/schemas.py

"""
기억 메모 API 의 입력과 응답의 모양.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.memory.models import NOTE_MAX_CHARS, NoteSource

NoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NOTE_MAX_CHARS)]


class NoteWrite(BaseModel):
    """메모를 쓰거나 고칠 때 받는 글."""

    model_config = ConfigDict(extra='forbid')

    text: NoteText


class NoteOut(BaseModel):
    """메모 하나. source 는 누가 썼는가(user, summary)다."""

    id: uuid.UUID
    text: str
    source: NoteSource
    created_at: datetime
    updated_at: datetime
