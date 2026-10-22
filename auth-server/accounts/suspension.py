# auth-server/accounts/suspension.py

"""
계정 정지와 정지 풀기(#274). 운영자가 관리 명령(suspend_account, restore_account)으로 한다.

정지는 네 가지를 한 트랜잭션에서 한다.
  1. 계정을 막는다(is_active). 로그인, refresh, 로그인 코드 확인이 모두 거부된다
  2. 세션 버전을 올린다. 이미 발급된 토큰이 인증 서버에서 바로 거부되고, 끊긴 세션 목록에 실려
     다른 서버에서도 30초 안에 거부된다(session_revocations.py)
  3. 정지의 기록(Suspension)을 적는다. 사유의 종류(SuspensionReason)와 사유다(#634)
  4. 보안 이벤트에 사유와 함께 남긴다

풀면 계정을 열고, 정지의 기록에 푼 시각과 사유를 적고, 보안 이벤트에 남긴다.
정지의 기록은 보안 이벤트(30일)보다 오래 남는다. 탈퇴를 마칠 때 정지 중인지와 그 사유를 본다.

관리자 화면에서 is_active 를 직접 끄지 못하게 한다(admin.py). 그 길로 끄면 2 가 빠져
다른 서버에서 옛 access 토큰이 만료(15분)까지 통한다.
"""

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from accounts.models import SecurityEvent, SecurityEventKind, Suspension, SuspensionReason, User
from accounts.security_events import record_security_event
from accounts.tokens import revoke_all_sessions

# 사유의 가장 긴 길이. 보안 이벤트의 칸(SecurityEvent.note)과 같다
MAX_NOTE_LENGTH = SecurityEvent._meta.get_field('note').max_length


class UnknownAccountError(Exception):
    """그런 아이디의 계정이 없다."""


class InvalidNoteError(ValueError):
    """사유가 비었거나 너무 길다."""


class UnknownReasonError(ValueError):
    """사유의 종류가 SuspensionReason 에 없다."""


def clean_note(note: str) -> str:
    """사유의 앞뒤 공백을 떼고 확인한다. 비었거나 MAX_NOTE_LENGTH 를 넘으면 InvalidNoteError."""
    cleaned = note.strip()
    if not cleaned:
        raise InvalidNoteError('사유를 적어야 합니다.')
    if len(cleaned) > MAX_NOTE_LENGTH:
        raise InvalidNoteError(f'사유는 {MAX_NOTE_LENGTH}자까지 적습니다.')
    return cleaned


def clean_reason(reason: str) -> SuspensionReason:
    """사유의 종류를 확인한다. 앞뒤 공백을 떼고 소문자로 맞춘다. 없는 종류면 UnknownReasonError."""
    try:
        return SuspensionReason(reason.strip().lower())
    except ValueError as exc:
        raise UnknownReasonError(reason) from exc


def find_account(username: str) -> User:
    """아이디로 계정을 찾는다. 아이디는 저장할 때처럼 소문자로 맞춘다. 없으면 UnknownAccountError."""
    user = User.objects.filter(username=User.normalize_username(username.strip())).first()
    if user is None:
        raise UnknownAccountError(username)
    return user


def _lock(user: User) -> User:
    """계정의 줄을 잠그고 지금 값으로 다시 읽는다. 정지와 풀기가 엇갈려도 한쪽씩 차례로 적힌다."""
    return User.objects.select_for_update().get(pk=user.pk)


@transaction.atomic
def suspend_account(user: User, note: str, *, reason: SuspensionReason) -> bool:
    """
    계정을 정지한다. 이미 정지된 계정이면 아무것도 하지 않고 False 를 돌려준다.

    사유는 부르는 쪽이 clean_note 로, 사유의 종류는 clean_reason 으로 확인한 것을 넘긴다.
    """
    locked = _lock(user)
    if not locked.is_active:
        return False
    locked.is_active = False
    locked.save(update_fields=['is_active'])
    revoke_all_sessions(locked)
    _open_suspension(locked, reason, note, timezone.now())
    record_security_event(kind=SecurityEventKind.ACCOUNT_SUSPENDED, user=locked, note=note)
    return True


def _open_suspension(user: User, reason: SuspensionReason, note: str, now: datetime) -> None:
    """정지의 기록을 한 줄 적는다. 풀리지 않은 기록이 이미 있으면 DB 의 제약이 막는다."""
    Suspension.objects.create(user=user, reason=reason, note=note, suspended_at=now)


@transaction.atomic
def restore_account(user: User, note: str) -> bool:
    """
    정지를 푼다. 정지되지 않은 계정이면 아무것도 하지 않고 False 를 돌려준다.

    세션 버전은 되돌리지 않는다. 정지 전의 토큰은 계속 쓸 수 없고, 사용자는 다시 로그인한다.
    """
    locked = _lock(user)
    if locked.is_active:
        return False
    locked.is_active = True
    locked.save(update_fields=['is_active'])
    _close_suspension(locked, note, timezone.now())
    record_security_event(kind=SecurityEventKind.ACCOUNT_RESTORED, user=locked, note=note)
    return True


def _close_suspension(user: User, note: str, now: datetime) -> None:
    """풀리지 않은 정지의 기록에 푼 시각과 사유를 적는다."""
    Suspension.objects.filter(user=user, restored_at__isnull=True).update(restored_at=now, restore_note=note)
