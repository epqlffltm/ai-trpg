# trpg-server/app/operators/schemas.py

"""
운영자 API 의 응답 모양. 일반 API 의 모양을 쓸 수 있으면 그것을 쓰고, 운영자에게만 더 보이는 것만 여기에 둔다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.operators.models import REASON_MAX_LENGTH
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


# 제재의 사유. 신고 번호나 짧은 글. 앞뒤 공백을 떼고 1~200자
ReasonText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)]


class ActionRequest(BaseModel):
    """제재를 할 때 받는 값(#392). 사유만 받는다. 누가 했는지는 토큰에서 읽는다."""

    model_config = ConfigDict(extra='forbid')

    reason: ReasonText


class SanctionOut(BaseModel):
    """시나리오를 제재한 결과."""

    scenario_id: uuid.UUID
    # 제재되어 다시 공개하지 못하는 판의 번호
    version_number: int
    owner_id: uuid.UUID
    # 제작자가 공개 금지 중인가. 이 제재로 정해진 수에 닿았으면 참이 된다
    publishing_banned: bool


class PublishingBanOut(BaseModel):
    """한 사람의 공개 금지."""

    user_id: uuid.UUID
    banned: bool
    banned_at: datetime
    # 금지한 운영자. 저절로 금지되었으면 None
    banned_by: uuid.UUID | None
    lifted_at: datetime | None
