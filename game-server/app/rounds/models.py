# game-server/app/rounds/models.py

"""
라운드의 모델. 라운드는 플레이의 한 바퀴다.

한 바퀴는 이렇게 돈다.
  1. GM 이 장면을 서술한다(scene). 첫 라운드의 장면은 테이블을 만들 때 고른 스타팅이다.
  2. 앉은 사람들이 각자 "나는 이것을 한다"를 적어 낸다(선언).
  3. 다 모이면 라운드가 닫히기 시작한다. 방장이 먼저 닫을 수도 있다. 더는 선언을 받지 않는다.
  4. GM 이 선언들을 한 번에 받아 결과를 서술한다. 서술하는 데는 시간이 걸린다.
  5. 서술이 끝나면 라운드가 닫히고, 그 서술이 다음 라운드의 장면이 된다.

라운드의 상태는 셋이다(RoundStatus). 열림(2) → 닫는 중(3, 4) → 닫힘(5).

테이블 둘이 있다.
  - table_rounds: 라운드. 테이블마다 번호가 1 부터 하나씩 올라간다.
  - round_declarations: 선언. 한 라운드에 한 사람이 하나씩 낸다.

닫힌 라운드와 그 선언은 고치지 않는다. 지나간 일의 기록이다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.assets.models import CHARACTER_NAME_MAX_LENGTH, at_most
from app.core.database import Base

# 선언 하나의 길이(글자 수). 라운드마다 사람 수만큼 AI 의 입력에 들어간다. 길이가 곧 비용이다
DECLARATION_MAX_LENGTH = 1000


class RoundStatus(enum.StrEnum):
    """라운드의 상태. 한 방향으로만 나아간다."""

    # 선언을 받는 중
    OPEN = 'open'
    # 선언을 마감했고 GM 이 결과를 서술하는 중. 선언을 낼 수 없다
    CLOSING = 'closing'
    # 서술이 끝났다. 다음 라운드가 열렸다
    CLOSED = 'closed'


class Round(Base):
    """
    라운드 하나. 장면 하나와, 그 장면에 대한 선언들이다.

    상태를 칸 하나에 적지 않고 시각 둘로 안다(status). 언제 그렇게 됐는지가 함께 남는다.
    """

    __tablename__ = 'table_rounds'
    __table_args__ = (
        CheckConstraint('number >= 1', name='number_positive'),
        # 한 테이블에 같은 번호의 라운드가 둘일 수 없다
        UniqueConstraint('table_id', 'number'),
        # 한 테이블에 닫히지 않은 라운드(열림, 닫는 중)는 하나뿐이다. 조건이 붙은 유일 색인이다.
        # 닫힌 라운드(closed_at 이 있는 것)는 이 색인에 들어가지 않으므로 몇 개든 된다.
        # 코드가 틀려서 라운드를 닫지 않고 새로 열어도, DB 가 막는다
        Index('uq_table_rounds_open', 'table_id', unique=True, postgresql_where='closed_at IS NULL'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 테이블의 라운드인가. 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'))

    # 테이블 안에서의 순서. 1 부터 하나씩 올라간다
    number: Mapped[int] = mapped_column(Integer)

    # 이 라운드를 여는 장면. GM 의 서술이다. 앉은 사람 모두에게 보인다.
    # 첫 라운드는 스타팅이고, 그 뒤로는 앞 라운드의 선언들에 대한 결과다
    scene: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 닫기 시작한 시각. 선언을 마감하고 서술을 맡긴 때다. 비어 있으면 아직 선언을 받는 중이다.
    # 서술을 다시 맡기면 이 시각을 지금으로 고친다. "맡긴 지 얼마나 됐나"를 이것으로 안다(app/rounds/service.py)
    closing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 닫힌 시각. 서술이 끝나 다음 라운드가 열린 때다
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 이 라운드의 선언들. 낸 순서다. 많아야 넷이라 라운드를 읽을 때 함께 읽는다
    declarations: Mapped[list['Declaration']] = relationship(
        lazy='selectin', cascade='all, delete-orphan', order_by='Declaration.created_at, Declaration.user_id'
    )

    @property
    def status(self) -> RoundStatus:
        """라운드의 상태. 시각 둘에서 읽는다."""
        if self.closed_at is not None:
            return RoundStatus.CLOSED
        if self.closing_at is not None:
            return RoundStatus.CLOSING
        return RoundStatus.OPEN


class Declaration(Base):
    """
    선언 하나. 한 사람이 한 라운드에 "나는 이것을 한다"고 적어 낸 글이다.

    선언은 하려는 일이다. 결과가 아니다. 되는지 안 되는지는 엔진이 정한다.
    글(content)은 사람과 서술자가 읽고, 행동(action)은 엔진이 읽는다.
    """

    __tablename__ = 'round_declarations'
    __table_args__ = (CheckConstraint(at_most('content', DECLARATION_MAX_LENGTH), name='content_length'),)

    # 두 칸을 합쳐 기본 키로 삼는다. 한 사람이 한 라운드에 선언을 둘 낼 수 없다.
    # 라운드의 행이 지워지면 함께 지워진다
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('table_rounds.id', ondelete='CASCADE'), primary_key=True)
    # 인증 서버의 public_id
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    # 선언할 때의 캐릭터 이름. 자리(table_members)에서 복사해 둔다.
    # 이 사람이 나중에 테이블을 떠나도 기록에 누구의 선언이었는지 남는다
    character_name: Mapped[str] = mapped_column(String(CHARACTER_NAME_MAX_LENGTH))

    content: Mapped[str] = mapped_column(Text)

    # 행동. 선언의 글을 엔진이 읽을 수 있는 모양으로 적은 것이다(app/engine/action.py). 문서 하나다.
    # 비어 있으면 판정이 없는 선언이다(대화, 둘러보기). 그 테이블의 규칙에 맞는지는 받을 때 검사했다
    action: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
