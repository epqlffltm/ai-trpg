# asset-server/app/notifications/models.py

"""
asset 서버의 발송함. 칸과 규칙은 공용 코드에 있다(server_core/notifications/models.py).
표는 이 서버의 Base 로 만든다. 다른 서버의 마이그레이션에 섞이지 않는다.
"""

from server_core.notifications.models import OutgoingNotificationColumns

from app.core.database import Base


class OutgoingNotification(OutgoingNotificationColumns, Base):
    """알림 서버에 보낼 알림 하나."""
