# chat-server/app/operators/models.py

"""
운영자의 감사 기록(#678). docs/architecture/operators.md 의 "감사 기록"과 같은 칸이다.

  - operator_reads: 운영자가 신고에 굳힌 대화의 글을 본 기록. 볼 때마다 한 줄이다(사적 대화라 보는 일 자체를 남긴다)
  - operator_actions: 운영자가 신고를 처리한 기록. 할 때마다 한 줄이다
둘 다 덧붙이기만 한다. 고치기와 지우기는 DB 의 트리거가 막는다(마이그레이션). 본 내용은 싣지 않는다.
신고와 대화에 외래 키를 걸지 않는다. 기록은 그것들보다 오래 산다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.reports.models import one_of

# 사유의 가장 긴 길이(trpg-server, asset-server 와 같다)
REASON_MAX_LENGTH = 200


class ReadKind(enum.StrEnum):
    """운영자가 본 것의 종류."""

    # 신고에 굳힌 대화의 글(target_id 는 신고)
    MESSAGE_REPORT = 'message_report'


class ActionKind(enum.StrEnum):
    """운영자가 한 일의 종류. target_id 는 신고다."""

    REPORT_ACTION = 'report_action'
    REPORT_DISMISS = 'report_dismiss'


class OperatorRead(Base):
    """운영자가 남의 것을 한 번 본 일."""

    __tablename__ = 'operator_reads'
    __table_args__ = (
        CheckConstraint(one_of('target_kind', ReadKind), name='target_kind_allowed'),
        CheckConstraint(f'char_length(reason) <= {REASON_MAX_LENGTH}', name='reason_length'),
        CheckConstraint("btrim(reason) <> ''", name='reason_not_blank'),
        Index('ix_operator_reads_operator', 'operator_id', 'read_at'),
        Index('ix_operator_reads_target', 'target_id', 'read_at'),
        # 테스트가 테이블을 비울 때 DELETE 대신 TRUNCATE 를 쓰게 하는 표시(tests/cleaning.py). 트리거가 DELETE 를 막는다
        {'info': {'append_only': True}},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_kind: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 왜 보았는가. 신고 번호나 짧은 글
    reason: Mapped[str] = mapped_column(String(REASON_MAX_LENGTH))
    request_id: Mapped[str | None] = mapped_column(String(128))


class OperatorAction(Base):
    """운영자가 한 일 한 번. 덧붙이기만 한다."""

    __tablename__ = 'operator_actions'
    __table_args__ = (
        CheckConstraint(one_of('action', ActionKind), name='action_allowed'),
        CheckConstraint(f'char_length(reason) <= {REASON_MAX_LENGTH}', name='reason_length'),
        CheckConstraint("btrim(reason) <> ''", name='reason_not_blank'),
        Index('ix_operator_actions_operator', 'operator_id', 'acted_at'),
        Index('ix_operator_actions_target', 'target_id', 'acted_at'),
        {'info': {'append_only': True}},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(String(REASON_MAX_LENGTH))
    request_id: Mapped[str | None] = mapped_column(String(128))
