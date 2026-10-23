# shared/server-core/src/server_core/notifications/models.py

"""
발송함의 칸. 알림 서버에 보낼 알림을 한 줄씩 적는다.

표는 서버마다 자기 Base 로 만든다. 한 서버의 표가 다른 서버의 마이그레이션에 섞이지 않게 한다(server_core/database.py).

    class OutgoingNotification(OutgoingNotificationColumns, Base):
        pass

알림을 정한 일과 같은 트랜잭션에 적는다. 그래서 일만 남고 알림이 사라지거나, 알림만 가고 일은 되돌려지는 일이 없다.
알림 서버를 부르는 것은 그 뒤에 뒤에서 하는 작업이다(dispatcher.py).

한 줄의 일생.
  - pending: 보낼 차례를 기다린다. 보내지 못하면(알림 서버가 죽었다) 기다리는 시간을 늘려 다시 보낸다
  - 보내면(알림 서버가 받았다) 줄을 지운다. 알림의 기록은 알림 서버에 있다
  - failed: 알림 서버가 받지 않았다(같은 열쇠로 다른 알림, 모양이 틀렸다). 버그다.
    사람이 보도록 남기고 다시 보내지 않는다
  - 오래(dispatcher.STALE_AFTER, 7일) 보내지 못한 pending 은 보내지 않고 지운다. 그만큼 지난 알림은 이미 쓸모가 없다

source_key 는 알림 서버가 같은 알림을 알아보는 열쇠다. 다시 보내도, 서버 둘이 함께 보내도 알림 서버에는 한 줄이다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, Integer, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

TABLE_NAME = 'outgoing_notifications'
# 알림 서버의 상한과 같다(notification-server/app/notifications/models.py)
SOURCE_KEY_MAX_LENGTH = 128
KIND_MAX_LENGTH = 64
# 보내지 못한 까닭의 이름의 길이
ERROR_MAX_LENGTH = 40
STATUS_MAX_LENGTH = 20


class OutboxStatus(enum.StrEnum):
    """발송함의 한 줄의 상태. 보낸 줄은 지우므로 상태가 없다."""

    PENDING = 'pending'
    FAILED = 'failed'


# 보낼 차례를 찾는 색인의 조건. 마이그레이션도 같은 글자를 쓴다
PENDING_CONDITION = f"status = '{OutboxStatus.PENDING}'"
# 상태가 정해진 것 가운데 하나라는 조건
STATUS_CONDITION = 'status IN (' + ', '.join(f"'{status}'" for status in OutboxStatus) + ')'


class OutgoingNotificationColumns:
    """알림 서버에 보낼 알림 하나의 칸. 서버의 Base 와 함께 물려받아 표를 만든다."""

    __tablename__ = TABLE_NAME

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple:
        """제약과 색인. 표마다 새로 만든다(같은 객체를 두 표에 걸 수 없다)."""
        return (
            CheckConstraint(STATUS_CONDITION, name='status_allowed'),
            CheckConstraint('attempts >= 0', name='attempts_not_negative'),
            # 보낼 차례가 된 것을 찾는다. 기다리는 것만 담는다
            Index('ix_outgoing_notifications_due', 'next_attempt_at', postgresql_where=text(PENDING_CONDITION)),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    # 알림 서버가 같은 알림을 알아보는 열쇠. 서버 안에서도 하나다
    source_key: Mapped[str] = mapped_column(String(SOURCE_KEY_MAX_LENGTH), unique=True)

    # 받는 사람. 인증 서버의 public_id 다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    # 무슨 일인가. 점으로 나눈 소문자(character.hidden)
    kind: Mapped[str] = mapped_column(String(KIND_MAX_LENGTH))

    # 알림의 내용. 알림 서버가 그대로 사용자에게 내준다. 비밀과 남에게 보이면 안 되는 글을 넣지 않는다
    payload: Mapped[dict] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(STATUS_MAX_LENGTH), default=OutboxStatus.PENDING)

    # 보내지 못한 횟수. 다시 보내기까지 기다리는 시간이 이것으로 정해진다
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    # 다음에 보낼 시각. 비어 있으면 바로 보낸다(처음 적은 것). 보내지 못하면 기다릴 만큼 뒤로 적는다
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 적은 시각. 오래 보내지 못한 것을 지울 때 본다
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 마지막으로 보내지 못한 까닭(unavailable 의 이름이나 알림 서버의 답). 사람이 보는 것이다
    last_error: Mapped[str | None] = mapped_column(String(ERROR_MAX_LENGTH))
