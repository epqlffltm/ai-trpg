# game-server/app/chat/models.py

"""
테이블의 채팅. 앉은 사람들이 서로 이야기하는 곳이다.

게임의 진행과 별개다. 선언은 GM 에게 "나는 이것을 한다"고 내는 것이고, 채팅은 플레이어끼리 합을 맞추는 말이다.
AI 는 채팅을 보지 않는다. 서술자의 입력에 들어가지 않는다.

이벤트 기록(app/events/models.py)에 넣지 않고 따로 둔다. 채팅은 게임에서 일어난 사실이 아니고 양이 많다.
이벤트를 되돌리기나 AI 의 입력에 쓸 때 채팅이 섞여 있으면 매번 걸러 내야 한다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import CHARACTER_NAME_MAX_LENGTH, at_most
from app.core.database import Base

# 채팅 한 줄의 길이(글자 수). 합을 맞추는 짧은 말이다. 긴 글은 선언에 쓴다
MESSAGE_MAX_LENGTH = 500


class ChatMessage(Base):
    """
    채팅 한 줄.

    sequence 는 테이블 안에서의 순서다. 1 부터 빈 번호 없이 올라간다. 이벤트의 번호와는 따로 센다.
    고치거나 지우지 않는다.
    """

    __tablename__ = 'table_messages'
    __table_args__ = (
        CheckConstraint('sequence >= 1', name='sequence_positive'),
        CheckConstraint(at_most('content', MESSAGE_MAX_LENGTH), name='content_length'),
        # 한 테이블에 같은 번호의 글이 둘일 수 없다.
        # 이 조건이 만드는 색인이 "이 테이블의 N 번 뒤"를 찾는 데도 쓰인다
        UniqueConstraint('table_id', 'sequence'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 테이블의 채팅인가. 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'))

    # 테이블 안에서의 순서. 테이블이 센다(game_tables.last_message_sequence)
    sequence: Mapped[int] = mapped_column(Integer)

    # 쓴 사람. 인증 서버의 public_id 다.
    # 화면은 이 값으로 자리(table_members)를 찾아 그 사람의 지금 캐릭터 이름을 보여 준다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    # 쓸 때의 캐릭터 이름. 자리에서 복사해 둔다. 아직 캐릭터를 정하지 않았으면 비어 있다.
    # 쓴 사람이 테이블을 떠나면 자리가 지워진다. 그때 누구의 글이었는지 알려 주는 것은 이 값뿐이다
    character_name: Mapped[str | None] = mapped_column(String(CHARACTER_NAME_MAX_LENGTH))

    content: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
