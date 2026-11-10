# story-server/app/records/models.py

"""
본 엔딩의 표(ending_records), 연 일러스트의 표(illustration_unlocks), 받은 업적의 표(achievement_records)와
플레이한 사람의 표(world_players). 스키마는 story 다.

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
        ForeignKey('conversations.id', ondelete='SET NULL'), default=None, index=True
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
        ForeignKey('conversations.id', ondelete='SET NULL'), default=None, index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AchievementRecord(Base):
    """
    사람 하나가 세계관 하나에서 업적 하나를 처음 받은 것(docs/architecture/achievements.md 의 "story").
    업적은 제작자가 작품에 단 것이다(스팀의 업적과 같다). 인증 서버의 활동 배지와는 다른 것이다.
    다시 채워도 처음 받은 때와 세션 그대로다. 이름, 받는 법, 그림은 받은 때의 판의 것이다
    (숨긴 업적도 받은 사람에게는 보인다).
    """

    __tablename__ = 'achievement_records'

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # 세계관마다 받은 사람을 센다(달성률). 기본 키는 사람이 앞이라 따로 색인을 둔다
    world_source: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)
    achievement_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default='', server_default='')
    image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('conversations.id', ondelete='SET NULL'), default=None, index=True
    )
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorldPlayer(Base):
    """
    사람 하나가 세계관 하나를 플레이한 것. 그 세계관의 세션에서 말이나 행동을 한 번이라도 보낸 사람이다.
    업적의 달성률의 분모다. 이 표가 생긴 뒤부터 센다.
    """

    __tablename__ = 'world_players'

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # 세계관마다 플레이한 사람을 센다
    world_source: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)
    first_played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
