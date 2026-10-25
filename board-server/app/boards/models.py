# board-server/app/boards/models.py

"""
게시판의 테이블. 게시판의 종류는 표에 두고 내용은 마이그레이션으로 넣는다(관리 API 는 없다).

표와 칸, 제약의 이름은 NestJS(TypeORM)로 쓰던 때와 같다(#785). 같은 board 스키마를 그대로 넘겨받는다.
그래서 이름을 규칙(NAMING_CONVENTION)으로 짓지 않고 conv() 로 그대로 적는다.
"""

import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Identity, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import conv

from app.core.database import Base

SLUG_MAX_LENGTH = 30
NAME_MAX_LENGTH = 50
DESCRIPTION_MAX_LENGTH = 200
WRITE_POLICY_MAX_LENGTH = 20


class WritePolicy(enum.StrEnum):
    """누가 글을 쓸 수 있는가. 댓글은 어느 게시판이든 로그인한 사람이 쓴다."""

    MEMBER = 'member'
    OPERATOR = 'operator'


class Board(Base):
    """게시판 하나. 공지사항, 이벤트, 자유 게시판, 시나리오 이야기."""

    __tablename__ = 'boards'
    __table_args__ = (
        CheckConstraint("write_policy IN ('member', 'operator')", name=conv('ck_boards_write_policy')),
        UniqueConstraint('slug', name=conv('uq_boards_slug')),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    # 주소에 쓰는 이름(free, notice)
    slug: Mapped[str] = mapped_column(String(SLUG_MAX_LENGTH))
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    description: Mapped[str] = mapped_column(String(DESCRIPTION_MAX_LENGTH))
    write_policy: Mapped[str] = mapped_column(String(WRITE_POLICY_MAX_LENGTH))
    # 목록에 보이는 차례. 작은 것이 먼저다
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
