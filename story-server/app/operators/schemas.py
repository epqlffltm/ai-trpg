# story-server/app/operators/schemas.py

"""
운영자 API 의 입력과 응답의 모양(chat 의 #678 과 같다).
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.operators.models import REASON_MAX_LENGTH
from app.reports.models import ReportOutcome, ReportReason

# 운영자가 보거나 처리하는 사유. 신고 번호나 짧은 글. 비어 있으면 422 다
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)]


class ReportSummaryOut(BaseModel):
    """열린 신고의 한 줄. 세션의 글은 싣지 않는다(열어 볼 때 감사 기록과 함께 준다). 신고한 사람의 id 도 없다."""

    id: uuid.UUID
    world_id: uuid.UUID
    world_version: int
    world_name: str
    model_slug: str | None
    reason: ReportReason
    created_at: datetime


class ReportPage(BaseModel):
    """열린 신고의 한 쪽과 전체 수."""

    items: list[ReportSummaryOut]
    total: int


class ContextMessageOut(BaseModel):
    """신고에 굳힌 앞의 말 하나. role 은 user, assistant, action 이다."""

    role: str
    content: str


class ReportDetailOut(ReportSummaryOut):
    """신고 하나와 굳힌 글. 볼 때마다 감사 기록에 남는다."""

    description: str
    content: str
    context: list[ContextMessageOut]
    handled_at: datetime | None
    outcome: ReportOutcome | None


class OutcomeInput(BaseModel):
    """신고의 처리. reason 은 감사 기록의 사유다. 처리는 기록일 뿐 세계관을 숨기지 않는다."""

    model_config = ConfigDict(extra='forbid')

    outcome: ReportOutcome
    reason: Reason
