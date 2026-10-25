# board-server/app/comments/models.py

"""
댓글과 답글의 테이블. 답글은 parent_id 가 댓글을 가리킨다(한 단계만, 답글에 단 답글은 없다).

지운 댓글은 지운 시각만 적고 행을 남긴다. 답글이 남은 지운 댓글은 목록에 자리만 남는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKeyConstraint, Identity, Index, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import conv

from app.core.database import Base


class Comment(Base):
    """댓글이나 답글 하나."""

    __tablename__ = 'comments'
    __table_args__ = (
        ForeignKeyConstraint(['post_id'], ['posts.id'], name=conv('fk_comments_post'), ondelete='RESTRICT'),
        ForeignKeyConstraint(['parent_id'], ['comments.id'], name=conv('fk_comments_parent'), ondelete='RESTRICT'),
        # 글의 댓글 목록(댓글과 그 답글)
        Index(conv('ix_comments_post_id_parent_id_id'), 'post_id', 'parent_id', 'id'),
        # 쓰기 한도(사람마다 최근에 쓴 것)
        Index(conv('ix_comments_author_id_created_at'), 'author_id', 'created_at'),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    post_id: Mapped[int] = mapped_column(BigInteger)
    parent_id: Mapped[int | None] = mapped_column(BigInteger)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
