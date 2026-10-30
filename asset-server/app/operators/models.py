# asset-server/app/operators/models.py

"""
운영자가 한 조치의 감사 기록(operator_actions, #678). docs/architecture/operators.md 의 "감사 기록"과 같은 칸이다.

  - 덧붙이기만 한다. 고치기와 지우기는 DB 의 트리거가 막는다(마이그레이션). 코드에도 그런 문장이 없다
  - 조치와 한 트랜잭션에서 적는다. 조치가 되지 않았으면 기록도 없다
  - 캐릭터와 세계관에 외래 키를 걸지 않는다. 기록은 그것들보다 오래 산다
  - 운영자가 남의 것을 "보는" 기록(operator_reads)은 아직 없다. 지금의 운영자 API 는 신고의 목록(운영자에게 보낸 것)과
    공개된 판만 본다. 비공개 초안이나 대화를 보는 API 를 만들 때 함께 둔다
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.reports.models import one_of

# 사유의 가장 긴 길이(trpg-server 와 같다)
REASON_MAX_LENGTH = 200


class ActionKind(enum.StrEnum):
    """운영자가 한 조치의 종류. target_id 는 캐릭터의 조치면 캐릭터, 세계관의 조치면 세계관이다."""

    # 캐릭터를 숨겼다(공개 목록과 남의 새 대화에서 내렸다). 신고를 받아들인 것도 이것이다
    CHARACTER_HIDE = 'character_hide'
    # 숨김을 풀었다
    CHARACTER_UNHIDE = 'character_unhide'
    # 그 캐릭터의 열린 신고를 받아들이지 않았다
    REPORTS_DISMISS = 'reports_dismiss'
    # 세계관을 숨겼다(공개 목록과 남의 새 세션에서 내렸다). story 의 신고를 보고 운영자가 한다
    WORLD_HIDE = 'world_hide'
    # 세계관의 숨김을 풀었다
    WORLD_UNHIDE = 'world_unhide'


class OperatorAction(Base):
    """운영자가 한 조치 한 번. 덧붙이기만 한다(트리거가 고치기와 지우기를 막는다)."""

    __tablename__ = 'operator_actions'
    __table_args__ = (
        CheckConstraint(one_of('action', ActionKind), name='action_allowed'),
        CheckConstraint(f'char_length(reason) <= {REASON_MAX_LENGTH}', name='reason_length'),
        CheckConstraint("btrim(reason) <> ''", name='reason_not_blank'),
        Index('ix_operator_actions_operator', 'operator_id', 'acted_at'),
        Index('ix_operator_actions_target', 'target_id', 'acted_at'),
        # 테스트가 테이블을 비울 때 DELETE 대신 TRUNCATE 를 쓰게 하는 표시(tests/cleaning.py). 트리거가 DELETE 를 막는다
        {'info': {'append_only': True}},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # 조치한 운영자. 토큰의 sub 다
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 왜 했는가. 신고 번호나 짧은 글
    reason: Mapped[str] = mapped_column(String(REASON_MAX_LENGTH))
    # 그 요청의 식별자(관측 규격의 request_id). 로그와 잇는다
    request_id: Mapped[str | None] = mapped_column(String(128))
