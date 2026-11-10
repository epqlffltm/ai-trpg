# chat-server/app/achievements/models.py

"""
받은 업적의 표(achievement_records)와 대화한 사람의 표(character_players). 계정마다다
(docs/architecture/achievements.md 의 "chat").

업적은 제작자가 캐릭터에 단 것이다(스팀의 업적과 같다). 인증 서버의 활동 배지와는 다른 것이다.
캐릭터는 asset 서버의 캐릭터 id(character_source)로 가리킨다. 판이 바뀌어도 같은 캐릭터의 기록이다.
받은 대화(conversation_id)는 그 대화가 지워지면 비운다. 기록은 남는다. 탈퇴하면 지운다(app/withdrawal/).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.world.models import KEY_MAX_LENGTH


class AchievementRecord(Base):
    """
    사람 하나가 캐릭터 하나에서 업적 하나를 처음 받은 것. 다시 채워도 처음 받은 때와 대화 그대로다.
    이름, 받는 법, 그림은 받은 때의 판의 것이다(숨긴 업적도 받은 사람에게는 보인다).
    """

    __tablename__ = 'achievement_records'

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # 캐릭터마다 받은 사람을 센다(달성률). 기본 키는 사람이 앞이라 따로 색인을 둔다
    character_source: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)
    achievement_id: Mapped[str] = mapped_column(String(KEY_MAX_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default='', server_default='')
    image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('conversations.id', ondelete='SET NULL'), default=None, index=True
    )
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CharacterPlayer(Base):
    """
    사람 하나가 캐릭터 하나와 대화한 것. 그 캐릭터와의 대화에서 답을 한 번이라도 받은 사람이다.
    업적의 달성률의 분모다. 이 표가 생긴 뒤부터 센다.
    """

    __tablename__ = 'character_players'

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # 캐릭터마다 대화한 사람을 센다
    character_source: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)
    first_played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
