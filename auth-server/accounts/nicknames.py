# auth-server/accounts/nicknames.py

"""
본인이 닉네임을 바꾸는 것과, 버린 닉네임을 묶어 두는 것.

  - 30일에 한 번 바꾼다(NICKNAME_CHANGE_INTERVAL). 이름을 자꾸 바꿔 남을 흉내 내거나 신고를 피하지 못하게 한다
  - 버린 이름은 30일 동안 다른 사람이 가져가지 못한다(RELEASED_NICKNAME_HOLD, ReleasedNickname).
    버린 사람은 그 안에 다시 가져갈 수 있다. 계정을 비울 때(탈퇴, 만 14세 미만, erasure.py)의 이름도 같이 묶는다
  - 묶는 기간이 지난 줄은 정리 명령(manage.py delete_released_nicknames, 하루 한 번)이 지운다.
    탈퇴한 사람의 옛 이름이 기간 뒤에도 남지 않게 한다
  - 비밀번호는 부르는 쪽(views.MyNicknameView)이 먼저 확인한다. 비밀번호 변경과 같은 횟수 한도를 쓴다

다른 서버는 access 토큰의 닉네임을 본다(tokens.py). 바꾼 뒤 새 access 토큰을 받을 때까지 그 서버에는 옛 이름이 보인다.
화면은 바꾼 직후에 갱신을 한 번 한다. 관리자 화면에서 고친 것은 이 규칙을 거치지 않는다(운영자가 직접 고친다).
"""

from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import ReleasedNickname, User

NICKNAME_CHANGE_INTERVAL = timedelta(days=30)
RELEASED_NICKNAME_HOLD = timedelta(days=30)


class NicknameChangeTooSoonError(Exception):
    """마지막으로 바꾼 뒤 NICKNAME_CHANGE_INTERVAL 이 지나지 않았다."""

    def __init__(self, available_at: datetime) -> None:
        super().__init__(available_at)
        self.available_at = available_at


class NicknameUnchangedError(Exception):
    """지금의 닉네임과 같다."""


class WrongNicknamePasswordError(Exception):
    """닉네임을 바꾸며 적은 비밀번호가 틀렸다."""


class NicknameTakenError(Exception):
    """다른 계정이 쓰고 있거나, 다른 사람이 버려 묶여 있다. 사용자에게는 둘을 가리지 않는다."""


def check_nickname_password(user: User, password: str) -> None:
    """
    닉네임을 바꾸며 적은 비밀번호를 확인한다. 틀리면 WrongNicknamePasswordError.

    열린 채 둔 기기에서 남이 이름을 바꾸지 못하게 한다. 횟수는 부르는 쪽이 비밀번호 변경의 한도로 센다.
    """
    if not user.check_password(password):
        raise WrongNicknamePasswordError


def nickname_change_available_at(user: User, now: datetime | None = None) -> datetime | None:
    """다음에 바꿀 수 있는 시각. 지금 바꿀 수 있으면 None 이다."""
    if user.nickname_changed_at is None:
        return None
    available_at = user.nickname_changed_at + NICKNAME_CHANGE_INTERVAL
    return available_at if available_at > (now or timezone.now()) else None


def is_nickname_held(nickname: str, *, for_user: User | None = None, now: datetime | None = None) -> bool:
    """
    다른 사람이 버려 묶여 있는 이름인가. for_user 가 버린 것이면 묶이지 않은 것으로 본다(제 이름을 되찾는다).

    가입(services.complete_signup)과 바꾸기가 함께 쓴다. 가입할 때는 for_user 가 없다.
    """
    held = ReleasedNickname.objects.filter(nickname=nickname, held_until__gt=now or timezone.now())
    if for_user is not None:
        held = held.exclude(released_by=for_user)
    return held.exists()


def change_nickname(user: User, new_nickname: str) -> User:
    """
    본인의 닉네임을 바꾸고, 바꾼 시각을 적고, 옛 이름을 묶어 둔다. 바뀐 계정을 돌려준다.

    new_nickname 의 형식과 예약어는 부르는 쪽이 먼저 본다(serializers.NicknameChangeSerializer).
    계정의 줄을 잠그고 본다. 같은 사람이 두 번 동시에 보내도 30일 한도를 한 번에 두 번 쓰지 못한다.
    """
    now = timezone.now()
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        _ensure_change_allowed(locked, new_nickname, now)
        old_nickname = locked.nickname
        _save_new_nickname(locked, new_nickname, now)
        hold_released_nickname(old_nickname, locked, now)
        # 제가 버렸던 이름을 되찾았으면 묶어 둔 줄은 더 필요 없다
        ReleasedNickname.objects.filter(nickname=new_nickname, released_by=locked).delete()
    return locked


def _ensure_change_allowed(user: User, new_nickname: str, now: datetime) -> None:
    """바꿀 수 있는지 본다. 아니면 까닭에 맞는 예외를 낸다."""
    available_at = nickname_change_available_at(user, now)
    if available_at is not None:
        raise NicknameChangeTooSoonError(available_at)
    if new_nickname == user.nickname:
        raise NicknameUnchangedError
    if User.objects.filter(nickname=new_nickname).exclude(pk=user.pk).exists():
        raise NicknameTakenError
    if is_nickname_held(new_nickname, for_user=user, now=now):
        raise NicknameTakenError


def _save_new_nickname(user: User, new_nickname: str, now: datetime) -> None:
    """새 이름과 바꾼 시각을 적는다. 사전 조회 뒤에 다른 요청이 먼저 가져갔으면 DB 의 유일 제약이 막는다."""
    user.nickname = new_nickname
    user.nickname_changed_at = now
    try:
        # 유일 제약에 걸리면 이 안쪽만 되돌린다. 바깥의 잠금과 트랜잭션은 그대로다
        with transaction.atomic():
            user.save(update_fields=['nickname', 'nickname_changed_at'])
    except IntegrityError as exc:
        raise NicknameTakenError from exc


def hold_released_nickname(nickname: str, user: User, now: datetime) -> None:
    """
    버린 이름을 묶어 둔다. 같은 이름의 지난 줄이 있으면 새로 덮는다.

    바꾸기(change_nickname)와 계정 비우기(erasure.blank_account)가 부른다. 부르는 쪽이 계정의 줄을 잠근 트랜잭션 안이다.
    """
    ReleasedNickname.objects.update_or_create(
        nickname=nickname,
        defaults={'released_by': user, 'held_until': now + RELEASED_NICKNAME_HOLD},
    )


def delete_expired_released_nicknames(now: datetime | None = None) -> int:
    """묶는 기간이 지난 줄을 지우고, 지운 개수를 돌려준다. 정리 명령이 하루 한 번 부른다."""
    deleted_count, _ = ReleasedNickname.objects.filter(held_until__lte=now or timezone.now()).delete()
    return deleted_count
