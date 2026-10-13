# game-server/app/whispers/models.py

"""
테이블 안의 1:1 쪽지(#196). 앉은 사람끼리 다른 사람 몰래 주고받는다.

사람마다 쪽지함이 있다. 쪽지 하나를 보내면 보낸 사람의 쪽지함과 받은 사람의 쪽지함에 한 줄씩 적는다.
번호(sequence)도 쪽지함마다 센다.

채팅의 표(table_messages)에 받는 사람의 칸을 더하지 않은 까닭: 채팅의 번호는 테이블에서 빈 번호 없이 올라간다.
쪽지가 그 번호를 쓰면 남들에게는 번호가 건너뛰는 것이 보인다. 쪽지가 오간 것이 새어 나간다.
쪽지함마다 번호를 세면 내 번호는 나와 상관있는 쪽지로만 올라가서 빈 번호가 없다.
같은 글이 두 줄 남는 것이 값이다. 쪽지는 짧다(500자까지).

AI 는 보내는 쪽이 허락한 쪽지(gm_visible)만 본다. 그 라운드의 서술에 숨은 정보로 들어간다(app/rounds/prompt.py).
고치거나 지우지 않는다. 테이블이 지워지면 함께 지워진다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import CHARACTER_NAME_MAX_LENGTH, at_most
from app.chat.models import MESSAGE_MAX_LENGTH
from app.core.database import Base

# 쪽지 한 장의 길이(글자 수). 채팅 한 줄과 같다
WHISPER_MAX_LENGTH = MESSAGE_MAX_LENGTH

# 서술자에게 줄 쪽지라는 조건. 보낸 사람의 쪽지함에 있는 것만 센다(받은 사람의 것은 같은 쪽지의 사본이다).
# 마이그레이션(20261013_..._whispers.py)에 같은 글자가 있다
GM_CONDITION = 'gm_visible AND owner_id = sender_id'


class Whisper(Base):
    """
    쪽지함 하나에 적힌 쪽지 한 장.

    owner_id 의 쪽지함이다. 보낸 사람이거나 받은 사람이다.
    sequence 는 그 쪽지함 안에서의 순서다. 1 부터 빈 번호 없이 올라간다.
    """

    __tablename__ = 'table_whispers'
    __table_args__ = (
        CheckConstraint('sequence >= 1', name='sequence_positive'),
        CheckConstraint('round_number >= 1', name='round_number_positive'),
        CheckConstraint(at_most('content', WHISPER_MAX_LENGTH), name='content_length'),
        # 자기 자신에게는 보내지 않는다
        CheckConstraint('sender_id <> recipient_id', name='not_to_self'),
        # 쪽지함의 주인은 보낸 사람이거나 받은 사람이다. 제삼자의 쪽지함에 적히지 않는다
        CheckConstraint('owner_id IN (sender_id, recipient_id)', name='owner_is_party'),
        # 한 쪽지함에 같은 번호의 쪽지가 둘일 수 없다.
        # 이 조건이 만드는 색인이 "이 쪽지함의 N 번 뒤"를 찾는 데도 쓰인다
        UniqueConstraint('table_id', 'owner_id', 'sequence'),
        # 서술할 때 "이 라운드에 GM 에게 보인 쪽지"를 찾는다
        Index('ix_table_whispers_gm', 'table_id', 'round_number', postgresql_where=text(GM_CONDITION)),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 테이블의 쪽지인가. 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'))

    # 누구의 쪽지함인가. 인증 서버의 public_id 다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    # 그 쪽지함 안에서의 순서. 테이블을 잠근 채로 "지금까지의 가장 큰 번호 + 1"로 정한다
    sequence: Mapped[int] = mapped_column(Integer)

    sender_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    recipient_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    # 보낼 때의 캐릭터 이름. 자리에서 복사해 둔다. 아직 캐릭터를 정하지 않았으면 비어 있다.
    # 떠난 사람의 자리는 지워진다. 그때 누구였는지 알려 주는 것은 이 값뿐이다(채팅과 같다)
    sender_character_name: Mapped[str | None] = mapped_column(String(CHARACTER_NAME_MAX_LENGTH))
    recipient_character_name: Mapped[str | None] = mapped_column(String(CHARACTER_NAME_MAX_LENGTH))

    content: Mapped[str] = mapped_column(Text)

    # GM(AI)에게 보이는가. 보내는 쪽이 고른다. 기본은 보이지 않는다
    gm_visible: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))

    # 어느 라운드의 서술에 들어가는가. 보낼 때 정한다(service.target_round).
    # 그 라운드가 닫기 시작하면 더 늘지 않는다. 서술을 다시 맡겨도 서술자는 같은 쪽지를 받는다
    round_number: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
