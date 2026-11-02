# chat-server/app/bookmarks/schemas.py

"""
책갈피 API 의 입력과 응답의 모양.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.bookmarks.models import BOOKMARK_NOTE_MAX_CHARS
from app.conversations.models import Role

# 목록에 보이는 말의 앞부분(글자)
EXCERPT_CHARS = 80

BookmarkNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=BOOKMARK_NOTE_MAX_CHARS)]


class BookmarkWrite(BaseModel):
    """책갈피를 달 때 받는 것. 메모는 없어도 된다(비우면 메모가 없다)."""

    model_config = ConfigDict(extra='forbid')

    note: BookmarkNote | None = None


class BookmarkOut(BaseModel):
    """
    책갈피 하나. 그 말의 역할과 앞부분(excerpt)을 함께 싣는다(목록에서 어느 말인지 알아보게).
    그 자리로 가려면 가지 고르기(PUT /conversations/{id}/branch, message_id)를 부른다.
    다른 가지의 말이면 그 가지가 보인다.
    """

    message_id: uuid.UUID
    note: str | None
    role: Role
    excerpt: str
    created_at: datetime
