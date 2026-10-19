# trpg-server/app/notifications/client.py

"""
알림 서버를 부르는 것. 요청마다 서명하고(결제 서버와 같은 모양, app/billing/signing.py), 답을 결과로 바꾼다.

주소와 답의 뜻은 알림 서버가 정했다(notification-server/README.md 의 "알림 넣기").

| 답 | 결과 |
| --- | --- |
| 201(새로 넣었다), 200(이미 있다) | 보냈다(DELIVERED) |
| 401, 408, 429, 5xx, 연결 실패, 시간 초과 | 다시 보낼 일(UNAVAILABLE) |
| 409(같은 열쇠로 다른 알림), 413, 422, 그 밖의 4xx | 받지 않았다(REJECTED). 버그다 |

401 은 서명이 거절된 것이다. 두 서버의 비밀이 다르거나 시계가 5분 넘게 어긋났다. 설정을 고치면 낫는 일이라
다시 보낼 일로 둔다(결제 서버를 부를 때와 같다). 그동안 발송함에 쌓인다.

우리 서버라서 추적의 머리말(traceparent)을 싣는다. 알림 서버의 로그와 trace_id 로 이어진다.
"""

import enum
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import SecretStr

from app.billing.signing import SIGNATURE_HEADER, sign
from app.notifications.models import OutgoingNotification
from app.observability.context import outgoing_headers

# 게임 서버가 알림을 넣는 주소. 주소에 넣는 서버의 이름(game)이 들어간다
PUT_PATH = '/api/v1/notification/service/game/notifications'

# 다시 보내면 될 수 있는 답. 서명 거절(401), 시간 초과(408), 너무 많음(429)
RETRYABLE_CLIENT_ERRORS = frozenset({401, 408, 429})


class Delivery(enum.StrEnum):
    """알림 하나를 보낸 결과."""

    DELIVERED = 'delivered'
    UNAVAILABLE = 'unavailable'
    REJECTED = 'rejected'


@dataclass(frozen=True)
class Sent:
    """보낸 결과와 그 까닭의 이름(보내지 못했을 때). 까닭은 발송함과 로그에 남는다."""

    delivery: Delivery
    reason: str | None = None


class Notifications(Protocol):
    """알림을 보내는 것의 모양. 테스트는 가짜를 꽂는다."""

    async def send(self, notification: OutgoingNotification) -> Sent:
        """알림 하나를 보낸다. 예외를 올리지 않고 결과로 돌려준다."""
        ...


def encode(notification: OutgoingNotification) -> bytes:
    """보낼 본문. 이 바이트에 서명하고 이 바이트를 보낸다. 알림 서버가 모르는 칸은 넣지 않는다(422)."""
    body = {
        'source_key': notification.source_key,
        'user_id': str(notification.user_id),
        'kind': notification.kind,
        'payload': notification.payload,
    }
    return json.dumps(body, separators=(',', ':'), ensure_ascii=False).encode()


def result_of(response: httpx.Response) -> Sent:
    """알림 서버의 답을 결과로 바꾼다. 위의 표다."""
    if response.is_success:
        return Sent(Delivery.DELIVERED)
    code = response.status_code
    if code == 401:
        return Sent(Delivery.UNAVAILABLE, 'unauthorized')
    if code >= 500 or code in RETRYABLE_CLIENT_ERRORS:
        return Sent(Delivery.UNAVAILABLE, f'status_{code}')
    return Sent(Delivery.REJECTED, f'status_{code}')


@dataclass(frozen=True)
class HttpNotifications:
    """
    알림 서버를 부르는 것. client 는 앱이 함께 쓰는 httpx 클라이언트다. 닫는 것은 앱이 한다.

    clock 은 서명에 적는 지금 시각(초)이다. 테스트가 시각을 정해 꽂는다.
    """

    client: httpx.AsyncClient
    base_url: str
    secret: SecretStr
    timeout: float
    clock: Callable[[], float] = time.time

    def headers_for(self, body: bytes) -> dict[str, str]:
        """보낼 머리말. 서명과 추적이다."""
        signature = sign(self.secret.get_secret_value(), int(self.clock()), 'POST', PUT_PATH, body)
        return {'Content-Type': 'application/json', SIGNATURE_HEADER: signature, **outgoing_headers()}

    async def send(self, notification: OutgoingNotification) -> Sent:
        """알림 하나를 보낸다. 답을 받지 못하면 다시 보낼 일이다."""
        body = encode(notification)
        url = self.base_url.rstrip('/') + PUT_PATH
        try:
            response = await self.client.post(url, content=body, headers=self.headers_for(body), timeout=self.timeout)
        except httpx.TimeoutException:
            return Sent(Delivery.UNAVAILABLE, 'timeout')
        except httpx.HTTPError:
            return Sent(Delivery.UNAVAILABLE, 'unreachable')
        return result_of(response)
