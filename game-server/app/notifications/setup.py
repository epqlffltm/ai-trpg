# game-server/app/notifications/setup.py

"""
설정으로 알림 서버를 부르는 것을 만든다. 앱을 만들 때(app/main.py) 부른다.

NOTIFICATION_URL 을 비우면 None 이다. 그때 알림은 발송함에 적히기만 하고 보내지 않는다(테스트, 알림 서버 없는 개발).
"""

import httpx

from app.core.config import Settings
from app.notifications.client import HttpNotifications


def build_notifications(settings: Settings, client: httpx.AsyncClient) -> HttpNotifications | None:
    """알림 서버를 부르는 것. 주소가 없으면 None."""
    base_url = settings.notification_url.strip()
    if not base_url:
        return None
    return HttpNotifications(
        client=client,
        base_url=base_url,
        secret=settings.notification_secret,
        timeout=settings.notification_timeout_seconds,
    )
