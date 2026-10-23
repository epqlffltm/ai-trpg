# asset-server/app/reports/models.py

"""
공개 캐릭터의 신고(character_reports, #678).

  - 같은 사람이 같은 캐릭터를 두 번 신고하지 못한다(유일 제약). 처리된 뒤에도 그렇다(게시판의 신고와 같다)
  - 운영자가 처리하면 처리한 시각, 처리한 사람, 결과를 함께 적는다. 셋은 함께 있거나 함께 없다.
    처리하지 않은 신고가 "열린 신고"다
  - 신고는 고치지 않는다. 처리한 것만 적는다
  - 캐릭터를 지우면 신고도 지워진다(외래 키의 CASCADE). 공개한 캐릭터를 지우면 공개도 끝난다(문제가 된 것이 사라진다)
  - version 은 신고한 사람이 본 판의 번호다. 그 뒤에 고친 판이 나와도 무엇을 보고 신고했는지 안다
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 설명의 가장 긴 길이(게시판의 신고와 같다)
DESCRIPTION_MAX_LENGTH = 500


class ReportReason(enum.StrEnum):
    """
    신고의 사유. 게시판의 다섯에 minor(미성년 인물을 성적으로 다룬다)를 더했다(2026-10-23 유저 결정).
    minor 는 약관이 금지하는 선이라 운영자의 목록에서 가장 먼저 보인다.
    """

    SPAM = 'spam'
    ABUSE = 'abuse'
    SEXUAL = 'sexual'
    MINOR = 'minor'
    ILLEGAL = 'illegal'
    OTHER = 'other'


class ReportOutcome(enum.StrEnum):
    """처리의 결과. 받아들였다(캐릭터를 숨겼다), 받아들이지 않았다."""

    ACTIONED = 'actioned'
    DISMISSED = 'dismissed'


def one_of(column: str, values: type[enum.StrEnum]) -> str:
    """칸의 값이 열거의 값 가운데 하나라는 CHECK 의 식."""
    allowed = ', '.join(f"'{value}'" for value in values)
    return f'{column} IN ({allowed})'


class CharacterReport(Base):
    """신고 하나."""

    __tablename__ = 'character_reports'
    __table_args__ = (
        CheckConstraint(one_of('reason', ReportReason), name='reason_allowed'),
        CheckConstraint(f'outcome IS NULL OR {one_of("outcome", ReportOutcome)}', name='outcome_allowed'),
        CheckConstraint(
            '(handled_at IS NULL) = (handled_by IS NULL) AND (handled_at IS NULL) = (outcome IS NULL)',
            name='handled_together',
        ),
        UniqueConstraint('reporter_id', 'character_id', name='uq_character_reports_reporter_character'),
        # 운영자의 목록: 열린 신고를 캐릭터마다 묶는다
        Index('ix_character_reports_open', 'character_id', postgresql_where='handled_at IS NULL'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('characters.id', ondelete='CASCADE'))
    # 신고한 사람(인증 서버의 public_id)
    reporter_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 신고한 사람이 본 판의 번호
    version: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text, default='', server_default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    handled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    outcome: Mapped[str | None] = mapped_column(String(20), default=None)
