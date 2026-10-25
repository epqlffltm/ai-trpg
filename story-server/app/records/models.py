# story-server/app/records/models.py

"""
본 엔딩의 표(ending_records). 스키마는 story 다.

세계관은 asset 서버의 id(world_source)로 가리킨다. 판이 바뀌어도 같은 세계관의 기록이다.
본 세션(conversation_id)은 그 세션이 지워지면 비운다. 기록은 남는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EndingRecord(Base):
    """사람 하나가 세계관 하나에서 엔딩 하나를 처음 본 것. 다시 봐도 처음 본 시각과 세션은 그대로다."""

    __tablename__ = 'ending_records'

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    world_source: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    ending_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('conversations.id', ondelete='SET NULL'), default=None
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
