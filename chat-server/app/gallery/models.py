# chat-server/app/gallery/models.py

"""
연 이벤트 씬의 기록(scene_unlocks, #669). 계정마다다.

해금 대상(collectible)인 이벤트 씬이 대화에서 처음 나오면 한 줄을 적는다. 한 사람, 한 캐릭터, 한 이벤트 씬에 한 줄이다.
대화를 가리키지 않는다. 가지를 바꾸거나 대화를 지워도 한 번 연 것은 열린 채로 둔다(화면 명세 C7).
캐릭터는 asset 서버의 캐릭터 id(character_source)로 가리킨다. 판이 바뀌어도 같은 이벤트 씬은 같은 id 다.
탈퇴하면 지운다(app/withdrawal/).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.world.models import KEY_MAX_LENGTH


class SceneUnlock(Base):
    """연 이벤트 씬 하나. unlocked_at 은 처음 연 시각이고 다시 열어도 바뀌지 않는다."""

    __tablename__ = 'scene_unlocks'
    __table_args__ = (
        # 내가 연 것의 목록: 최근에 연 것부터
        Index('ix_scene_unlocks_owner_unlocked', 'owner_id', 'unlocked_at'),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    character_source: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    scene_id: Mapped[str] = mapped_column(String(KEY_MAX_LENGTH), primary_key=True)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
