# auth-server/accounts/suspension.py

"""
계정 정지와 정지 풀기(#274). 운영자가 관리 명령(suspend_account, restore_account)으로 한다.

정지는 세 가지를 한 트랜잭션에서 한다.
  1. 계정을 막는다(is_active). 로그인, refresh, 로그인 코드 확인이 모두 거부된다
  2. 세션 버전을 올린다. 이미 발급된 토큰이 인증 서버에서 바로 거부되고, 끊긴 세션 목록에 실려
     다른 서버에서도 30초 안에 거부된다(session_revocations.py)
  3. 보안 이벤트에 사유와 함께 남긴다

관리자 화면에서 is_active 를 직접 끄지 못하게 한다(admin.py). 그 길로 끄면 2 가 빠져
다른 서버에서 옛 access 토큰이 만료(15분)까지 통한다.
"""

from django.db import transaction

from accounts.models import SecurityEvent, SecurityEventKind, User
from accounts.security_events import record_security_event
from accounts.tokens import revoke_all_sessions

# 사유의 가장 긴 길이. 보안 이벤트의 칸(SecurityEvent.note)과 같다
MAX_NOTE_LENGTH = SecurityEvent._meta.get_field('note').max_length


class UnknownAccountError(Exception):
    """그런 아이디의 계정이 없다."""


class InvalidNoteError(ValueError):
    """사유가 비었거나 너무 길다."""


def clean_note(note: str) -> str:
    """사유의 앞뒤 공백을 떼고 확인한다. 비었거나 MAX_NOTE_LENGTH 를 넘으면 InvalidNoteError."""
    cleaned = note.strip()
    if not cleaned:
        raise InvalidNoteError('사유를 적어야 합니다.')
    if len(cleaned) > MAX_NOTE_LENGTH:
        raise InvalidNoteError(f'사유는 {MAX_NOTE_LENGTH}자까지 적습니다.')
    return cleaned


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
def suspend_account(user: User, note: str) -> bool:
    """
    계정을 정지한다. 이미 정지된 계정이면 아무것도 하지 않고 False 를 돌려준다.

    사유는 부르는 쪽이 clean_note 로 확인한 것을 넘긴다.
    """
    locked = _lock(user)
    if not locked.is_active:
        return False
    locked.is_active = False
    locked.save(update_fields=['is_active'])
    revoke_all_sessions(locked)
    record_security_event(kind=SecurityEventKind.ACCOUNT_SUSPENDED, user=locked, note=note)
    return True


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
    record_security_event(kind=SecurityEventKind.ACCOUNT_RESTORED, user=locked, note=note)
    return True
