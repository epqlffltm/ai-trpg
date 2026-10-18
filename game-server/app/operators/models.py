# game-server/app/operators/models.py

"""
운영자가 남의 것을 본 기록(operator_reads, #391). 볼 때마다 한 줄이다.

규칙(docs/architecture/operators.md 의 "감사 기록").
  - 덧붙이기만 한다. 고치기와 지우기는 DB 의 트리거가 막는다(마이그레이션). 코드에도 그런 문장이 없다.
  - 무엇을 보았는지만 적는다. 본 내용은 싣지 않는다.
  - 테이블과 시나리오에 외래 키를 걸지 않는다. 기록은 그것들보다 오래 산다. 없는 ID 를 본 시도도 남긴다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import at_most, one_of
from app.core.database import Base

# 사유의 가장 긴 길이
REASON_MAX_LENGTH = 200


class ReadKind(enum.StrEnum):
    """운영자가 본 것의 종류."""

    # 테이블 하나(상태, 앉은 사람, 굳힌 판의 내용 전부)
    TABLE = 'table'
    # 테이블의 기록(서술, 행동, 판정)
    TABLE_EVENTS = 'table_events'
    # 테이블 대화
    TABLE_MESSAGES = 'table_messages'
    # 테이블의 귓속말 전부
    TABLE_WHISPERS = 'table_whispers'
    # 시나리오의 초안
    SCENARIO = 'scenario'
    # 시나리오의 판 하나(target_number 가 판의 번호)
    SCENARIO_VERSION = 'scenario_version'


class OperatorRead(Base):
    """운영자가 남의 것을 한 번 본 일."""

    __tablename__ = 'operator_reads'
    __table_args__ = (
        CheckConstraint(one_of('target_kind', ReadKind), name='target_kind_allowed'),
        CheckConstraint(at_most('reason', REASON_MAX_LENGTH), name='reason_length'),
        CheckConstraint("btrim(reason) <> ''", name='reason_not_blank'),
        # 누가 무엇을 보았는지 사람마다, 대상마다 찾는다
        Index('ix_operator_reads_operator', 'operator_id', 'read_at'),
        Index('ix_operator_reads_target', 'target_id', 'read_at'),
        # 테스트가 테이블을 비울 때 DELETE 대신 TRUNCATE 를 쓰게 하는 표시(tests/cleaning.py). 트리거가 DELETE 를 막는다
        {'info': {'append_only': True}},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    # 본 운영자. 토큰의 sub(인증 서버의 public_id)다
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    # 본 시각. 서버의 시계다
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    target_kind: Mapped[str] = mapped_column(String(30))
    # 테이블이나 시나리오의 ID
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 시나리오의 판이면 그 번호. 그 밖에는 비어 있다
    target_number: Mapped[int | None] = mapped_column(Integer)

    # 왜 보았는가. 신고 번호나 짧은 글
    reason: Mapped[str] = mapped_column(String(REASON_MAX_LENGTH))

    # 그 요청의 식별자(관측 규격의 request_id). 로그와 잇는다
    request_id: Mapped[str | None] = mapped_column(String(128))
