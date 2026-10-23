# shared/server-core/src/server_core/notifications/setup.py

"""
설정으로 알림 서버를 부르는 것을 만든다. 서버가 앱을 만들 때(app/main.py) 부른다.

NOTIFICATION_URL 을 비우면 None 이다. 그때 알림은 발송함에 적히기만 하고 보내지 않는다.
"""

import httpx

from server_core.notifications.client import HttpNotifications
from server_core.notifications.settings import NotificationSettings


def build_notifications(
    settings: NotificationSettings, client: httpx.AsyncClient, source: str
) -> HttpNotifications | None:
    """source 라는 서버로서 알림 서버를 부르는 것. 주소가 없으면 None."""
    base_url = settings.notification_url.strip()
    if not base_url:
        return None
    return HttpNotifications(
        client=client,
        base_url=base_url,
        source=source,
        secret=settings.notification_secret,
        timeout=settings.notification_timeout_seconds,
    )
