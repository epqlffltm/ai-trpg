# trpg-server/app/notifications/models.py

"""
게임 서버의 발송함. 알림 서버에 보낼 알림을 한 줄씩 적는다.

칸, 상태, 제약과 색인의 규칙은 공용 코드에 있다(server_core/notifications/models.py, #589).
표는 이 서버의 Base 로 만든다. 다른 서버의 마이그레이션에 섞이지 않는다.

알림을 정한 일(이벤트)과 같은 트랜잭션에 적는다(app/notifications/outbox.py). 그래서 이벤트만 남고 알림이 사라지거나,
알림만 가고 일은 되돌려지는 일이 없다. 알림 서버를 부르는 것은 그 뒤에 뒤에서 하는 작업이다
(server_core/notifications/dispatcher.py).
"""

from server_core.notifications.models import OutboxStatus, OutgoingNotificationColumns

from app.core.database import Base

__all__ = ['OutboxStatus', 'OutgoingNotification']


class OutgoingNotification(OutgoingNotificationColumns, Base):
    """알림 서버에 보낼 알림 하나."""
