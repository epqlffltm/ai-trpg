# story-server/app/records/models.py

"""
본 엔딩의 표(ending_records)와 연 일러스트의 표(illustration_unlocks). 스키마는 story 다.

세계관은 asset 서버의 id(world_source)로 가리킨다. 판이 바뀌어도 같은 세계관의 기록이다.
본 세션(conversation_id)은 그 세션이 지워지면 비운다. 기록은 남는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
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


class IllustrationUnlock(Base):
    """
    사람 하나가 세계관 하나에서 장면 하나의 일러스트를 처음 연 것. 다시 열어도 처음 연 때 그대로다.

    장면은 종류(scene_kind: event, ending)와 판의 id(scene_id)로 가리킨다. 이벤트와 엔딩의 id 는 서로 겹칠 수 있다.
    image_id 는 연 때의 그림(asset 서버의 이미지)이다. 제작자가 새 판에서 그림을 바꿔도 연 그림을 보인다.
    cast 는 그 장면이 부르는 인물들(판의 장면 칸)이다. 비었으면 세계관의 그림이다.
    """

    __tablename__ = 'illustration_unlocks'

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    world_source: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    scene_kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    scene_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    image_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    cast: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default='{}')
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('conversations.id', ondelete='SET NULL'), default=None
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
