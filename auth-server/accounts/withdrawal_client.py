# auth-server/accounts/withdrawal_client.py

"""
다른 서버에 탈퇴를 알린다(#603, docs/architecture/withdrawal.md 의 "알리는 길").

모든 서버가 같은 모양의 주소로 받는다.

    POST /api/v1/<서버>/service/users/{public_id}/withdrawal
    본문: {"withdrawn_at": "2026-10-28T03:00:00+00:00"}
    답: 200 {"status": "processed"}

서버마다 다른 것은 주소의 앞(API 의 머리)과 설정의 이름(주소, 비밀)뿐이라 표(DESTINATIONS) 하나에 둔다.
비밀이 비어 있는 서버에는 보내지 않는다(is_configured). 그 서버가 받는 주소를 만들 때 비밀을 적는다.
이 모듈은 요청 하나를 보내고 결과를 읽는 일만 한다. 언제 보내고 언제 다시 보내는지는 withdrawal.py 가 정한다.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.conf import settings

from accounts.models import WithdrawalTarget
from accounts.service_client import ServiceUnavailableError, post_signed

# 받는 서버가 정리를 마쳤다는 답. 이미 정리했거나 그 사용자의 것이 없던 것도 같다
PROCESSED = 'processed'


@dataclass(frozen=True)
class Destination:
    """탈퇴를 알릴 서버 하나. 주소의 머리와, 주소와 비밀을 읽는 설정의 이름이다."""

    api_prefix: str
    url_setting: str
    secret_setting: str


# 서버마다의 받는 곳. 받는 쪽의 비밀 이름은 모두 AUTH_SERVER_SECRET 이다(인증 서버의 이 비밀과 같은 값)
DESTINATIONS: dict[str, Destination] = {
    WithdrawalTarget.BILLING: Destination('/api/v1/billing', 'BILLING_URL', 'BILLING_SECRET'),
    WithdrawalTarget.NOTIFICATION: Destination('/api/v1/notification', 'NOTIFICATION_URL', 'NOTIFICATION_SECRET'),
    WithdrawalTarget.GAME: Destination('/api/v1/game', 'GAME_URL', 'GAME_SECRET'),
    WithdrawalTarget.BOARD: Destination('/api/v1/board', 'BOARD_URL', 'BOARD_SECRET'),
    WithdrawalTarget.ASSET: Destination('/api/v1/asset', 'ASSET_URL', 'ASSET_SECRET'),
    WithdrawalTarget.CHAT: Destination('/api/v1/chat', 'CHAT_URL', 'CHAT_SECRET'),
    WithdrawalTarget.STORY: Destination('/api/v1/story', 'STORY_URL', 'STORY_SECRET'),
}


class WithdrawalUndeliveredError(ServiceUnavailableError):
    """탈퇴를 알리지 못했다. 나중에 다시 보낸다. 닿지 못했거나 200 processed 가 아닌 답이다."""


def is_configured(target: str) -> bool:
    """그 서버의 비밀이 있는가. 없으면 그 서버에는 보내지 않는다(알릴 줄은 쌓여 기다린다)."""
    return bool(getattr(settings, DESTINATIONS[target].secret_setting))


def configured_targets() -> list[str]:
    """지금 알릴 수 있는 서버들. 비밀이 있는 서버다."""
    return [target for target in DESTINATIONS if is_configured(target)]


def send_withdrawal(*, target: str, user_public_id: UUID, withdrawn_at: datetime) -> None:
    """
    그 서버에 그 사용자가 탈퇴했다고 알린다. 200 processed 가 아니면 WithdrawalUndeliveredError 다.

    같은 사용자로 여러 번 불러도 결과가 같다. 그것은 받는 서버가 지킨다.
    받는 서버가 이 주소를 아직 모르는 판이라 404 인 것도 다시 보낼 일이다.
    """
    destination = DESTINATIONS[target]
    path = f'{destination.api_prefix}/service/users/{user_public_id}/withdrawal'
    body = json.dumps({'withdrawn_at': withdrawn_at.isoformat()}).encode()
    status_code, text = post_signed(
        base_url=getattr(settings, destination.url_setting),
        secret=getattr(settings, destination.secret_setting),
        secret_name=destination.secret_setting,
        path=path,
        body=body,
        error=WithdrawalUndeliveredError,
    )
    if status_code != 200:
        raise WithdrawalUndeliveredError(f'{target} 가 {status_code} 로 답했다')
    _check_processed(target, text)


def _check_processed(target: str, text: bytes) -> None:
    """답의 status 가 processed 인지 본다. 아니면 WithdrawalUndeliveredError."""
    try:
        outcome = json.loads(text).get('status')
    except (ValueError, AttributeError) as exc:
        raise WithdrawalUndeliveredError(f'{target} 의 답을 읽지 못했다') from exc
    if outcome != PROCESSED:
        raise WithdrawalUndeliveredError(f'{target} 가 모르는 결과로 답했다')
