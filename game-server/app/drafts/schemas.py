# game-server/app/drafts/schemas.py

"""
장부 초안 API 의 응답 모양. 방장만 받는다.

줄 하나가 장부의 변경 하나다. 무엇을 바꾸자는지는 kind 로 가른다.
  - found_item: 누가(user_id, character_name) 무엇을(entry_id, name) 몇 개(count)
  - quest_change: 어느 퀘스트(entry_id, name)를 무엇에서(previous) 무엇으로(status)
이름은 초안을 쓸 때의 것이다. 그사이 캐릭터가 바뀌었을 수 있다. 받아들일 때 다시 본다.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class FoundItemOut(BaseModel):
    """물건을 손에 넣었다는 줄."""

    id: uuid.UUID
    kind: Literal['found_item']
    round: int
    user_id: uuid.UUID
    character_name: str | None
    entry_id: uuid.UUID
    name: str
    count: int
    created_at: datetime


class QuestChangeOut(BaseModel):
    """퀘스트의 상태가 바뀌었다는 줄."""

    id: uuid.UUID
    kind: Literal['quest_change']
    round: int
    entry_id: uuid.UUID
    name: str
    previous: str
    status: str
    created_at: datetime


# 줄 하나. kind 로 모양을 고른다
LedgerDraftOut = Annotated[FoundItemOut | QuestChangeOut, Field(discriminator='kind')]


class LedgerDraftList(BaseModel):
    """방장의 결정을 기다리는 줄들. 라운드와 쓴 순서다."""

    items: list[LedgerDraftOut]
