# chat-server/app/reports/schemas.py

"""
대화 속 답의 신고의 입력과 응답의 모양(#678). 운영자의 것은 app/operators/schemas.py 에 있다.
"""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.reports.models import DESCRIPTION_MAX_LENGTH, ReportReason


class ReportCreate(BaseModel):
    """신고할 때 받는 값. 사유가 other 면 설명이 있어야 한다(asset 의 신고와 같다)."""

    model_config = ConfigDict(extra='forbid')

    reason: ReportReason
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX_LENGTH)] = ''

    @model_validator(mode='after')
    def other_needs_a_description(self) -> Self:
        """사유가 기타면 무엇이 문제인지 적어야 한다."""
        if self.reason == ReportReason.OTHER and not self.description:
            raise ValueError('사유가 기타(other)면 설명을 적어야 합니다')
        return self


class ReportCreated(BaseModel):
    """접수한 신고."""

    id: uuid.UUID
    created_at: datetime
