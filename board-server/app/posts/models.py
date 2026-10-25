# board-server/app/posts/models.py

"""
글의 테이블. 지운 글은 지운 시각(deleted_at)만 적고 행을 남긴다(신고가 그 글을 가리킨다).

글쓴이(author_id)는 인증 서버의 public_id 다. 탈퇴하면 비운다(app/withdrawal/). 다른 서버의 표를 가리키지 않는다.
고정(pinned_at, pinned_until)은 둘 다 있거나 둘 다 없다. 끝나는 시각이 지나면 고정하지 않은 것으로 읽는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import conv

from app.core.database import Base

TITLE_MAX_LENGTH = 100


class Post(Base):
    """글 하나."""

    __tablename__ = 'posts'
    __table_args__ = (
        CheckConstraint('(pinned_at IS NULL) = (pinned_until IS NULL)', name=conv('ck_posts_pin_pair')),
        ForeignKeyConstraint(['board_id'], ['boards.id'], name=conv('fk_posts_board'), ondelete='RESTRICT'),
        # 게시판의 목록(최근 것부터)
        Index(conv('ix_posts_board_id_id'), 'board_id', 'id'),
        # 쓰기 한도(사람마다 최근에 쓴 것)
        Index(conv('ix_posts_author_id_created_at'), 'author_id', 'created_at'),
        # 게시판의 고정한 글
        Index(
            conv('ix_posts_board_id_pinned_until'),
            'board_id',
            'pinned_until',
            postgresql_where=text('pinned_until IS NOT NULL'),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    board_id: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pinned_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
