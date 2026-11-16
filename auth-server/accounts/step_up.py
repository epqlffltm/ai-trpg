# auth-server/accounts/step_up.py

"""
민감한 작업(청약철회, 카드 등록·바꾸기·지우기) 앞의 본인 확인(F5, 2026-11-14 결정).

  - 메일로 받은 코드로 확인하면 그 세션의 확인 창이 STEP_UP_WINDOW(10분) 동안 열린다
  - 창이 열린 동안 민감한 작업을 하면 창이 다시 STEP_UP_WINDOW 로 늘어난다
  - 늘어나도 마지막으로 실제로 확인한 때에서 STEP_UP_CAP(1시간)을 넘지 않는다. 뺏긴 세션이 창을 끝없이 늘리지 못한다
  - 창은 세션(토큰의 sid)마다 있다. 다른 기기에서 한 확인은 이 기기에 들지 않는다
  - 본인 확인을 끈 사람(User.step_up_disabled)은 창을 묻지 않는다. 결제 서버가 그 상태(disabled)를 받아
    카드 작업은 확인 없이 하고 청약철회는 받지 않는다. 끄는 일 자체는 창이 열린 동안에만 된다

창을 묻고 늘리는 것은 결제 서버다(서버끼리, accounts/step_up_views.py). 플레이·대화·충전 같은 보통의 작업은 묻지 않는다.
HTTP 와 메일을 모른다. 코드의 발급과 확인은 email_codes.py 의 장치를 쓴다(용도 step_up).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from django.db import transaction

from accounts.email_codes import consume_email_code
from accounts.models import EmailCodePurpose, StepUpWindow, User

# 한 번 확인하면 열리는 시간이자, 민감한 작업마다 다시 늘어나는 시간
STEP_UP_WINDOW = timedelta(minutes=10)
# 마지막으로 실제로 확인한 때에서 창이 열려 있을 수 있는 가장 긴 시간
STEP_UP_CAP = timedelta(hours=1)


class StepUpState(StrEnum):
    """결제 서버가 받는 창의 상태."""

    # 창이 열려 있다. 민감한 작업을 해도 된다(창이 늘어났다)
    OPEN = 'open'
    # 창이 닫혔거나 확인한 적이 없다. 화면이 본인 확인을 받아야 한다
    REQUIRED = 'required'
    # 본인 확인을 껐다. 카드 작업은 확인 없이, 청약철회는 받지 않는다(결제 서버가 정한다)
    DISABLED = 'disabled'


class StepUpSessionUnknownError(Exception):
    """토큰에 세션의 이름(sid)이 없다. 이 기능 전에 받은 토큰이다. 갱신하면 생긴다."""


class StepUpRequiredError(Exception):
    """창이 열려 있어야 하는 일(본인 확인 끄기)을 창이 닫힌 채 하려 했다."""


@dataclass(frozen=True)
class WindowStatus:
    """세션 하나의 창. 닫혀 있으면 expires_at 이 없다."""

    enabled: bool
    open: bool
    expires_at: datetime | None


def require_session(session_id: str | None) -> str:
    """토큰의 세션 이름. 없으면 StepUpSessionUnknownError."""
    if not session_id:
        raise StepUpSessionUnknownError
    return session_id


def window_status(user: User, session_id: str, now: datetime) -> WindowStatus:
    """그 세션의 창을 읽기만 한다(늘리지 않는다). 화면이 지금 확인이 필요한지 보는 데 쓴다."""
    window = StepUpWindow.objects.filter(user=user, session_id=session_id).first()
    is_open = window is not None and now < window.expires_at
    return WindowStatus(
        enabled=not user.step_up_disabled,
        open=is_open,
        expires_at=window.expires_at if is_open and window is not None else None,
    )


def verify_step_up(user: User, session_id: str, code: str, now: datetime) -> datetime:
    """
    메일 코드로 본인을 확인하고 그 세션의 창을 연다. 닫히는 시각을 돌려준다.

    코드가 틀리면 email_codes 의 InvalidEmailCodeError 가 그대로 올라간다(틀린 횟수는 그 전에 저장된다).
    코드의 소비와 창을 여는 것이 한 트랜잭션이다. 이 사람의 다른 세션에서 상한이 지난 창은 함께 지운다.
    """
    expires_at = now + STEP_UP_WINDOW

    def open_window() -> None:
        StepUpWindow.objects.update_or_create(
            user=user, session_id=session_id, defaults={'verified_at': now, 'expires_at': expires_at}
        )
        StepUpWindow.objects.filter(user=user, verified_at__lt=now - STEP_UP_CAP).delete()

    consume_email_code(user=user, purpose=EmailCodePurpose.STEP_UP, code=code, on_success=open_window)
    return expires_at


def extended_until(window: StepUpWindow, now: datetime) -> datetime:
    """창을 늘린 뒤의 닫히는 시각. 지금부터 STEP_UP_WINDOW 이되, 확인한 때에서 STEP_UP_CAP 을 넘지 않는다."""
    return min(now + STEP_UP_WINDOW, window.verified_at + STEP_UP_CAP)


def check_step_up(user: User, session_id: str, now: datetime) -> tuple[StepUpState, datetime | None]:
    """
    결제 서버가 민감한 작업 앞에서 묻는다. 창이 열려 있으면 늘리고 open 과 새 닫히는 시각을 돌려준다.

    본인 확인을 껐으면 disabled, 창이 닫혔거나 없으면 required 다. 늘리는 것과 읽는 것이 한 번에 되게 행을 잠근다.
    같은 세션의 두 요청이 동시에 와도 늘린 값이 하나로 맞는다.
    """
    if user.step_up_disabled:
        return StepUpState.DISABLED, None
    with transaction.atomic():
        window = StepUpWindow.objects.select_for_update().filter(user=user, session_id=session_id).first()
        if window is None or now >= window.expires_at:
            return StepUpState.REQUIRED, None
        window.expires_at = extended_until(window, now)
        window.save(update_fields=['expires_at'])
        return StepUpState.OPEN, window.expires_at


def set_step_up_enabled(user: User, session_id: str, enabled: bool, now: datetime) -> None:
    """
    민감한 작업의 본인 확인을 켜거나 끈다.

    끄는 것은 그 세션의 창이 열린 동안에만 된다(StepUpRequiredError). 뺏긴 세션이 확인 없이 끄지 못하게 한다.
    켜는 것은 언제든 된다.
    """
    if not enabled and not window_status(user, session_id, now).open:
        raise StepUpRequiredError
    User.objects.filter(pk=user.pk).update(step_up_disabled=not enabled)
    user.step_up_disabled = not enabled
