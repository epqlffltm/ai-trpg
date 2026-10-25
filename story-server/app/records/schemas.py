# story-server/app/records/schemas.py

"""
계정의 기록 API 가 내보내는 모양.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class EndingRecordOut(BaseModel):
    """본 엔딩 하나. ending_id 는 판의 엔딩의 id 다. 이름과 힌트는 판의 문서에 있다."""

    ending_id: str
    first_seen_at: datetime
    # 처음 본 세션. 그 세션이 지워졌으면 null 이다
    conversation_id: uuid.UUID | None


class EndingRecordList(BaseModel):
    """한 세계관에서 본 엔딩들. 처음 본 차례다."""

    items: list[EndingRecordOut]
