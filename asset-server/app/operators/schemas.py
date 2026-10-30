# asset-server/app/operators/schemas.py

"""
운영자 API 의 입력과 응답의 모양(#678).
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.operators.models import REASON_MAX_LENGTH
from app.reports.models import ReportOutcome, ReportReason

# 조치의 사유. 신고 번호나 짧은 글. 비어 있으면 422 다
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)]


class OpenReportGroupOut(BaseModel):
    """열린 신고를 캐릭터마다 묶은 한 줄. reasons 는 사유마다의 수다. hidden 은 이미 숨긴 캐릭터인가."""

    character_id: uuid.UUID
    name: str
    hidden: bool
    open_count: int
    reasons: dict[ReportReason, int]
    first_reported_at: datetime
    last_reported_at: datetime


class OpenReportPage(BaseModel):
    """열린 신고의 묶음 한 쪽과 전체 묶음의 수."""

    items: list[OpenReportGroupOut]
    total: int


class ReportOut(BaseModel):
    """신고 하나(운영자가 본다). 신고한 사람의 id 는 싣지 않는다. 처리하는 데 필요하지 않다."""

    id: uuid.UUID
    version: int
    reason: ReportReason
    description: str
    created_at: datetime
    handled_at: datetime | None
    outcome: ReportOutcome | None


class OutcomeInput(BaseModel):
    """열린 신고의 처리. actioned 면 캐릭터를 숨긴다. reason 은 감사 기록의 사유다."""

    model_config = ConfigDict(extra='forbid')

    outcome: ReportOutcome
    reason: Reason


class OutcomeResult(BaseModel):
    """처리한 신고의 수와, 처리한 뒤 캐릭터가 숨겨져 있는가."""

    handled: int
    hidden: bool


class HiddenInput(BaseModel):
    """숨기기(true)와 풀기(false). reason 은 감사 기록의 사유다."""

    model_config = ConfigDict(extra='forbid')

    hidden: bool
    reason: Reason


class HiddenResult(BaseModel):
    """조치한 뒤 캐릭터(또는 세계관)가 숨겨져 있는가."""

    hidden: bool
