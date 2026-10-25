# board-server/app/reports/models.py

"""
신고의 테이블. 신고 하나는 글이나 댓글 하나를 가리킨다(둘 중 하나만).

한 사람은 한 글(한 댓글)을 한 번만 신고한다. 처리한 뒤에도 다시 신고하지 못한다(같은 제약).
처리(handled_at, handled_by, outcome)는 셋이 함께 적힌다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import conv

from app.core.database import Base

REASON_MAX_LENGTH = 20
OUTCOME_MAX_LENGTH = 20


class ReportReason(enum.StrEnum):
    """신고의 사유."""

    SPAM = 'spam'
    ABUSE = 'abuse'
    SEXUAL = 'sexual'
    ILLEGAL = 'illegal'
    OTHER = 'other'


class ReportOutcome(enum.StrEnum):
    """처리의 결과. 조치함과 문제없음."""

    ACTIONED = 'actioned'
    DISMISSED = 'dismissed'


class Report(Base):
    """신고 하나."""

    __tablename__ = 'reports'
    __table_args__ = (
        CheckConstraint('(post_id IS NULL) <> (comment_id IS NULL)', name=conv('ck_reports_one_target')),
        CheckConstraint(
            "reason IN ('spam', 'abuse', 'sexual', 'illegal', 'other')",
            name=conv('ck_reports_reason'),
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('actioned', 'dismissed')",
            name=conv('ck_reports_outcome'),
        ),
        CheckConstraint(
            '(handled_at IS NULL) = (handled_by IS NULL) AND (handled_at IS NULL) = (outcome IS NULL)',
            name=conv('ck_reports_handled_together'),
        ),
        ForeignKeyConstraint(['post_id'], ['posts.id'], name=conv('fk_reports_post'), ondelete='RESTRICT'),
        ForeignKeyConstraint(['comment_id'], ['comments.id'], name=conv('fk_reports_comment'), ondelete='RESTRICT'),
        UniqueConstraint('reporter_id', 'post_id', name=conv('uq_reports_reporter_id_post_id')),
        UniqueConstraint('reporter_id', 'comment_id', name=conv('uq_reports_reporter_id_comment_id')),
        # 처리할 신고의 목록(열린 것만)
        Index(conv('ix_reports_open'), 'created_at', postgresql_where=text('handled_at IS NULL')),
        # 글과 댓글마다의 신고
        Index(conv('ix_reports_post_id'), 'post_id', postgresql_where=text('post_id IS NOT NULL')),
        Index(conv('ix_reports_comment_id'), 'comment_id', postgresql_where=text('comment_id IS NOT NULL')),
        # 쓰기 한도(사람마다 최근에 한 신고)
        Index(conv('ix_reports_reporter_id_created_at'), 'reporter_id', 'created_at'),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    post_id: Mapped[int | None] = mapped_column(BigInteger)
    comment_id: Mapped[int | None] = mapped_column(BigInteger)
    # 신고한 사람. 탈퇴하면 비운다
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(String(REASON_MAX_LENGTH))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    outcome: Mapped[str | None] = mapped_column(String(OUTCOME_MAX_LENGTH))
