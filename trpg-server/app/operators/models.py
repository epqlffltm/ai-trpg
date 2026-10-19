# trpg-server/app/operators/models.py

"""
운영자의 감사 기록과 제재의 상태(#391, #392).

  - operator_reads: 운영자가 남의 것을 본 기록. 볼 때마다 한 줄이다
  - operator_actions: 운영자가 한 제재의 기록(시나리오 제재, 테이블 끝내기, 공개 금지와 풀기). 할 때마다 한 줄이다
  - scenario_sanctions: 제재된 판. 그 판은 다시 공개하지 못한다. 공개 금지를 셀 때도 쓴다
  - publishing_bans: 공개 금지(블랙리스트). 사람마다 한 줄. 풀면 lifted_at 이 적힌다

감사 기록 둘의 규칙(docs/architecture/operators.md 의 "감사 기록").
  - 덧붙이기만 한다. 고치기와 지우기는 DB 의 트리거가 막는다(마이그레이션). 코드에도 그런 문장이 없다.
  - 무엇을 보았는지만 적는다. 본 내용은 싣지 않는다.
  - 테이블과 시나리오에 외래 키를 걸지 않는다. 기록은 그것들보다 오래 산다. 없는 ID 를 본 시도도 남긴다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Uuid
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


class ActionKind(enum.StrEnum):
    """운영자가 한 제재의 종류."""

    # 시나리오의 공개를 내리고 그 판을 다시 공개하지 못하게 했다(target_id 는 시나리오)
    SCENARIO_SANCTION = 'scenario_sanction'
    # 테이블을 끝냈다(target_id 는 테이블)
    TABLE_END = 'table_end'
    # 공개를 금지했다(target_id 는 사람). 저절로 금지된 것은 운영자가 한 일이 아니라 적지 않는다
    PUBLISHING_BAN = 'publishing_ban'
    # 공개 금지를 풀었다(target_id 는 사람)
    PUBLISHING_UNBAN = 'publishing_unban'


class OperatorAction(Base):
    """운영자가 한 제재 한 번. 덧붙이기만 한다(트리거가 고치기와 지우기를 막는다)."""

    __tablename__ = 'operator_actions'
    __table_args__ = (
        CheckConstraint(one_of('action', ActionKind), name='action_allowed'),
        CheckConstraint(at_most('reason', REASON_MAX_LENGTH), name='reason_length'),
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


class ScenarioSanction(Base):
    """
    제재된 판 하나. 그 판은 다시 공개하지 못한다. 고쳐서 새 판을 내면 그 판은 공개할 수 있다.

    판이 있는 동안 남는다. 판은 테이블이 쓰므로 지워지지 않는다(RESTRICT).
    제작자(owner_id)를 함께 적는다. 공개 금지는 사람마다 센다.
    """

    __tablename__ = 'scenario_sanctions'
    __table_args__ = (Index('ix_scenario_sanctions_owner', 'owner_id', 'sanctioned_at'),)

    # 판 하나에 제재 하나다. 제재된 판은 공개되지 않으므로 다시 제재될 일이 없다
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('scenario_versions.id', ondelete='RESTRICT'), primary_key=True
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    sanctioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(REASON_MAX_LENGTH))


class PublishingBan(Base):
    """
    한 사람의 공개 금지(블랙리스트). 사람마다 한 줄이다. lifted_at 이 비어 있으면 금지 중이다.

    저절로 금지되면 banned_by 가 비어 있다. 풀면 lifted_at, lifted_by 가 적힌다. 다시 금지되면 같은 줄을 다시 쓴다.
    풀린 뒤에는 lifted_at 뒤의 제재만 센다. 풀자마자 옛 제재로 다시 금지되지 않게.
    """

    __tablename__ = 'publishing_bans'

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    banned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    banned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(String(REASON_MAX_LENGTH))
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
