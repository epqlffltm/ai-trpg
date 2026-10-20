# notification-server/app/notifications/models.py

"""
알림함의 테이블. 사람 하나에게 간 알림 하나가 한 줄이다(#385).

알림의 글은 저장하지 않는다. 무슨 일인지(kind)와 그 일의 값(payload)만 적는다.
글로 바꾸는 것은 화면이 한다. 게임 서버의 이벤트(type + payload)와 같은 방식이다.
  - 문구를 고치거나 다른 말로 보일 때 저장된 알림을 고치지 않아도 된다
  - 넣는 서버가 사람에게 보일 문장을 만들지 않는다. 사용자의 글(시나리오 제목 등)이 문장에 섞여 깨지는 일이 없다

사용자가 끈 알림의 종류도 여기 둔다(NotificationMute, #525). 끈 종류의 알림은 넣을 때 걸러 적지 않는다.

같은 알림이 두 번 들어오지 않는다. 넣는 서버(source)가 알림마다 붙인 열쇠(source_key)가 같으면 한 줄이다.
넣는 서버는 받았다는 답을 못 받으면 같은 열쇠로 다시 보낸다(발송함과 재시도).
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, String, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 넣는 서버의 이름. 서버의 이름표(game, billing, board)와 같은 모양이다
SOURCE_MAX_LENGTH = 32
# 넣는 서버가 알림마다 붙이는 열쇠. 그 서버 안에서만 겹치지 않으면 된다(예: 'scenario-sanction:42')
SOURCE_KEY_MAX_LENGTH = 128
# 무슨 일인가. 화면이 이것을 보고 글을 고른다(예: 'scenario.sanctioned')
KIND_MAX_LENGTH = 64
# 일의 값(JSON)의 상한(바이트). 알림 하나에 큰 글을 싣지 못하게 한다. 원문은 그 일을 맡은 서버에 있다
PAYLOAD_MAX_BYTES = 4096


class Notification(Base):
    """사람 하나에게 간 알림 하나."""

    __tablename__ = 'notifications'
    __table_args__ = (
        # 같은 알림을 두 번 넣지 않는다. 다시 보낸 것은 이미 있는 줄로 답한다
        UniqueConstraint('source', 'source_key', name='uq_notifications_source_key'),
        CheckConstraint(r"source ~ '^[a-z][a-z0-9_-]*$'", name='source_format'),
        CheckConstraint(r"kind ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'", name='kind_format'),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name='payload_is_object'),
        CheckConstraint(f'octet_length(payload::text) <= {PAYLOAD_MAX_BYTES}', name='payload_size'),
        CheckConstraint('read_at IS NULL OR read_at >= created_at', name='read_after_created'),
        # 내 알림함: 최근 것부터 읽는다
        Index('ix_notifications_user_id_id', 'user_id', text('id DESC')),
        # 읽지 않은 수: 읽지 않은 줄만 담는 색인. 읽은 알림이 쌓여도 세는 일이 느려지지 않는다
        Index('ix_notifications_unread', 'user_id', postgresql_where=text('read_at IS NULL')),
        # 보관 기간이 지난 것을 지울 때 오래된 것부터 찾는다
        Index('ix_notifications_created_at', 'created_at'),
    )

    # 차례대로 오르는 번호. 목록의 커서로 쓴다(이 번호보다 작은 것)
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # 받는 사람. 인증 서버의 public_id(토큰의 sub)다. 이 서버는 회원 정보를 갖지 않는다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 넣은 서버(game, billing, board 등)
    source: Mapped[str] = mapped_column(String(SOURCE_MAX_LENGTH))
    # 넣은 서버가 붙인 열쇠. 다시 보내도 같은 값이다
    source_key: Mapped[str] = mapped_column(String(SOURCE_KEY_MAX_LENGTH))
    # 무슨 일인가
    kind: Mapped[str] = mapped_column(String(KIND_MAX_LENGTH))
    # 그 일의 값. 화면이 글을 만들 때 쓴다(예: 시나리오 ID, 모델 이름, 날짜)
    payload: Mapped[dict] = mapped_column(JSONB)
    # 이 서버가 받은 시각
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 읽은 시각. 읽지 않았으면 비어 있다
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationMute(Base):
    """
    사람 하나가 끈 알림의 종류 하나(#525). 줄이 있으면 꺼져 있고, 없으면 켜져 있다.

    끌 수 있는 종류는 표(app/notifications/catalog.py 의 mutable)가 정한다. DB 는 모른다.
    표에서 끌 수 없게 바뀐 종류의 줄이 남아 있어도 거르지 않는다(app/mutes/service.py 의 is_muted).
    """

    __tablename__ = 'notification_mutes'
    __table_args__ = (CheckConstraint(r"kind ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'", name='kind_format'),)

    # 끈 사람. 인증 서버의 public_id(토큰의 sub)다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # 끈 종류
    kind: Mapped[str] = mapped_column(String(KIND_MAX_LENGTH), primary_key=True)
    # 끈 시각
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
