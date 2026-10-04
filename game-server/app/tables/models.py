# game-server/app/tables/models.py

"""
테이블의 모델. 테이블은 시나리오의 판 하나를 가져와 AI GM 과 플레이하는 자리다.

테이블 둘이 있다.
  - game_tables: 테이블 자신. 방장, 어느 판에서 왔는지, 판의 복사본, 정원, 상태.
  - table_members: 테이블에 앉은 사람과 그 사람의 캐릭터.

판은 고치지 않는다. 테이블은 만들 때 판의 내용을 통째로 복사해 온다(content).
플레이하면서 바뀌는 것(죽은 NPC, 열린 문)은 이 복사본을 고친다. 같은 판으로 만든 다른 테이블에는 영향이 없다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.assets.models import (
    CHARACTER_DESCRIPTION_MAX_LENGTH,
    CHARACTER_NAME_MAX_LENGTH,
    TABLE_MAX_PLAYERS,
    TITLE_MAX_LENGTH,
    Rating,
    at_most,
    one_of,
)
from app.core.database import Base

# 초대 코드의 길이(글자 수). 코드를 아는 사람만 테이블에 들어온다
INVITE_CODE_LENGTH = 12


class TableStatus(enum.StrEnum):
    """테이블의 상태. 한 방향으로만 나아간다."""

    # 모집 중. 사람이 들어오고 캐릭터를 만든다
    RECRUITING = 'recruiting'
    # 진행 중. 방장이 시작했다. 새로 들어올 수 없고 캐릭터를 바꿀 수 없다
    PLAYING = 'playing'
    # 끝남. 방장이 끝냈거나 모두 나갔다
    ENDED = 'ended'


class GameTable(Base):
    """
    테이블 하나.

    방장은 테이블을 만든 사람이다. 방장이 나가면 남은 사람 중 가장 먼저 들어온 사람이 방장이 된다.
    """

    __tablename__ = 'game_tables'
    __table_args__ = (
        CheckConstraint(one_of('status', TableStatus), name='status_allowed'),
        CheckConstraint(one_of('rating', Rating), name='rating_allowed'),
        CheckConstraint(f'capacity BETWEEN 1 AND {TABLE_MAX_PLAYERS}', name='capacity_range'),
        CheckConstraint('opening_index >= 0', name='opening_index_not_negative'),
    )

    # API 주소에 드러나는 값이다. 순서대로 늘어나는 정수면 테이블이 몇 개인지 추측할 수 있다
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 방장. 인증 서버의 public_id 다. "내가 방장인 테이블"을 찾을 일이 있어 색인을 건다
    host_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    # 어느 판에서 왔는가. 플레이할 때는 읽지 않는다(content 를 읽는다). 출처를 남기는 것이다.
    # 제작자에게 수익을 나눌 때, 판이 바뀌었다고 알려 줄 때 쓴다.
    # RESTRICT: 테이블이 가리키는 판의 행은 지울 수 없다
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('scenario_versions.id', ondelete='RESTRICT'), index=True)

    # 시나리오의 제목. content 안에도 있지만, 목록을 보여 줄 때 큰 문서를 열지 않으려고 따로 둔다
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))

    # 판의 복사본. 플레이에 필요한 것이 이 안에 다 있다. 모양은 판의 것과 같다(scenarios/snapshot.py).
    # GM 전용 글이 들어 있다. 참가자에게 그대로 내주면 안 된다
    content: Mapped[dict] = mapped_column(JSONB)

    # 고른 스타팅. content 의 openings 에서 몇 번째인가(0 부터). 테이블을 만드는 사람이 고른다
    opening_index: Mapped[int] = mapped_column(SmallInteger)

    # 정원. 방장을 포함해 몇 명까지 앉는가
    capacity: Mapped[int] = mapped_column(SmallInteger)

    status: Mapped[str] = mapped_column(String(20), default=TableStatus.RECRUITING)

    # 등급. 판의 것을 복사해 둔다. 누가 들어올 수 있는지를 문서를 열지 않고 판단한다
    rating: Mapped[str] = mapped_column(String(20))

    # 초대 코드. 이 코드를 아는 사람이 테이블에 들어온다. 방장이 참가자를 내보내면 새로 만든다
    invite_code: Mapped[str] = mapped_column(String(INVITE_CODE_LENGTH), unique=True)

    # 로비의 목록에 보이는가. 지금은 늘 False 다. 로비를 만들 때 쓴다
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 방장이 시작한 시각과 테이블이 끝난 시각. 아직이면 비어 있다
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 앉은 사람들. 들어온 순서다. 많아야 넷이라 테이블을 읽을 때 함께 읽는다.
    # delete-orphan: 이 목록에서 빠진 행은 DB 에서도 지운다(나가기, 내보내기)
    members: Mapped[list['TableMember']] = relationship(
        lazy='selectin', cascade='all, delete-orphan', order_by='TableMember.joined_at, TableMember.user_id'
    )


class TableMember(Base):
    """
    테이블에 앉은 사람 하나와 그 사람의 캐릭터.

    캐릭터는 이름과 설명이다. 들어온 직후에는 아직 없다(character_name 이 비어 있다).
    프리젠에서 가져왔으면 어느 프리젠인지 적어 둔다. 가져온 뒤에 이름과 설명을 고쳐도 그 자리는 이 사람의 것이다.
    """

    __tablename__ = 'table_members'
    __table_args__ = (
        CheckConstraint(at_most('character_description', CHARACTER_DESCRIPTION_MAX_LENGTH), name='description_length'),
        # 프리젠 하나는 한 테이블에서 한 사람만 쓴다. 같은 인물이 둘이 될 수 없다.
        # 비어 있는 값(NULL)끼리는 겹치는 것으로 보지 않으므로, 직접 만든 캐릭터는 몇이든 된다
        UniqueConstraint('table_id', 'pregen_index'),
        # 캐릭터가 없는데 프리젠만 차지하고 있을 수 없다
        CheckConstraint('character_name IS NOT NULL OR pregen_index IS NULL', name='pregen_needs_character'),
    )

    # 두 칸을 합쳐 기본 키로 삼는다. 한 사람이 같은 테이블에 두 번 앉을 수 없다.
    # 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'), primary_key=True)
    # 인증 서버의 public_id. "내가 앉은 테이블"을 찾을 일이 있어 색인을 건다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)

    # 캐릭터의 이름. 비어 있으면 아직 캐릭터를 만들지 않은 것이다
    character_name: Mapped[str | None] = mapped_column(String(CHARACTER_NAME_MAX_LENGTH))
    # 캐릭터의 설명. 턴마다 AI 의 입력에 들어간다
    character_description: Mapped[str] = mapped_column(Text, default='')

    # 가져온 프리젠. content 의 pregens 에서 몇 번째인가(0 부터). 직접 만들었으면 비어 있다
    pregen_index: Mapped[int | None] = mapped_column(SmallInteger)

    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
