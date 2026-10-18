# game-server/app/operators/schemas.py

"""
운영자 API 의 응답 모양. 일반 API 의 모양을 쓸 수 있으면 그것을 쓰고, 운영자에게만 더 보이는 것만 여기에 둔다.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.whispers.schemas import WhisperOut


class OperatorMember(BaseModel):
    """테이블에 앉은 사람 한 명."""

    user_id: uuid.UUID
    joined_at: datetime


class OperatorTable(BaseModel):
    """
    운영자가 보는 테이블. 앉은 사람이 보는 것과 달리 굳힌 판의 내용(content)을 통째로 싣는다.

    content 에는 룰북의 진행 지침, 세계관의 GM 전용 설정, 로어북, GM 메모처럼 AI 에 들어가는 글이 모두 있다.
    """

    id: uuid.UUID
    title: str
    status: str
    rating: str
    host_id: uuid.UUID
    version_id: uuid.UUID
    created_at: datetime
    ended_at: datetime | None
    members: list[OperatorMember]
    content: dict


class OperatorWhisperPage(BaseModel):
    """테이블의 귓속말 전부의 한 쪽. 쪽지함이 아니라 테이블 전체라 total 로 넘긴다."""

    items: list[WhisperOut]
    total: int = Field(ge=0)
