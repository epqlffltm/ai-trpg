# auth-server/accounts/services.py

"""
accounts 앱의 도메인 로직.

HTTP 를 모른다. 요청과 응답 객체를 받지 않고, 검증이 끝난 값만 받는다.
그래서 뷰 없이도 테스트하고 다른 곳(관리 명령 등)에서 다시 쓸 수 있다.
"""

from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.email_codes import (
    EmailCodeCooldownError,
    EmailCodeLimitError,
    InvalidEmailCodeError,
    consume_email_code,
    issue_email_code,
    reserve_email_slot,
)
from accounts.mail import send_already_registered_notice, send_email_code
from accounts.models import EmailCodePurpose, User

# 인증을 끝내지 않은 계정을 보관하는 시간.
# 인증 코드의 발급 구간(1시간에 5회)과 같게 잡았다.
# 가입을 시작하고 1시간 안에, 최대 5번 코드를 받아 인증을 끝내면 된다
PENDING_ACCOUNT_LIFETIME = timedelta(hours=1)

FIELD_TAKEN_MESSAGES = {
    'username': '이미 사용 중인 아이디입니다.',
    'nickname': '이미 사용 중인 닉네임입니다.',
}


class DuplicateAccountError(Exception):
    """아이디, 이메일, 닉네임 중 하나가 이미 쓰이고 있어 계정을 만들 수 없다."""


class FieldTakenError(Exception):
    """아이디나 닉네임을 다른 계정이 쓰고 있다. 어느 필드인지와 안내 문구를 담는다."""

    def __init__(self, field: str):
        super().__init__()
        self.field = field
        self.message = FIELD_TAKEN_MESSAGES[field]


class InvalidCredentialsError(Exception):
    """
    아이디와 비밀번호로 사용자를 확인하지 못했다.

    아이디가 없는 경우, 비밀번호가 틀린 경우, 비활성 계정인 경우를 구분하지 않는다.
    구분하면 호출한 쪽이 그 차이를 응답에 실어 가입 여부를 알려 주게 된다.
    """


class EmailNotVerifiedError(Exception):
    """
    아이디와 비밀번호는 맞지만 이메일 인증을 끝내지 않은 계정이다.

    비밀번호가 맞을 때만 낸다. 비밀번호를 아는 사람에게만 알려 주므로
    계정이 있다는 사실이 새지 않는다.
    """


def start_signup(*, username: str, email: str, nickname: str, password: str) -> None:
    """
    회원가입을 시작한다. 미인증 계정을 만들고 인증 코드를 메일로 보낸다.

    이미 가입된 이메일이면 계정을 만들지 않고, 그 주소로 안내 메일을 보낸다.
    두 경우 모두 아무것도 돌려주지 않는다. 호출한 쪽이 둘을 구분할 수 없어야
    응답으로 이메일의 가입 여부가 드러나지 않는다.

    아이디나 닉네임을 다른 계정이 쓰고 있으면 FieldTakenError 를 낸다.
    """
    now = timezone.now()

    try:
        with transaction.atomic():
            _delete_expired_pending_accounts(username=username, nickname=nickname, now=now)
            _ensure_not_taken(username=username, nickname=nickname, email=email)

            # 이메일이 이미 가입돼 있든 아니든 해싱을 한 번 수행한다.
            # 가입된 경우에 건너뛰면 응답이 훨씬 빨라져, 걸린 시간으로 가입 여부가 드러난다
            password_hash = make_password(password)

            registered_user = _find_verified_user(email)
            if registered_user is None:
                pending_user = _save_pending_user(
                    username=username,
                    email=email,
                    nickname=nickname,
                    password_hash=password_hash,
                    now=now,
                )
    except IntegrityError as exc:
        # 사전 조회를 통과한 뒤 다른 요청이 같은 값으로 먼저 저장한 경우
        raise DuplicateAccountError from exc

    # 메일은 트랜잭션이 끝난 뒤에 보낸다.
    # 안에서 보내면 메일 서버를 기다리는 동안 DB 잠금을 쥐고 있게 되고,
    # 메일은 나갔는데 트랜잭션이 취소되는 경우도 생긴다
    if registered_user is None:
        _send_signup_code(pending_user)
    else:
        _send_already_registered_notice(registered_user)


def verify_signup(*, email: str, code: str) -> None:
    """
    가입 인증 코드를 확인하고 계정을 인증된 상태로 바꾼다.

    코드가 틀렸거나, 그 이메일로 진행 중인 가입이 없으면 InvalidEmailCodeError 를 낸다.
    두 경우를 구분하지 않는다.
    """
    user = _find_pending_user(email)
    if user is None:
        raise InvalidEmailCodeError

    consume_email_code(
        user=user,
        purpose=EmailCodePurpose.SIGNUP,
        code=code,
        # 코드 소비와 같은 트랜잭션에서 실행된다
        on_success=lambda: _mark_email_verified(user),
    )


def resend_signup_code(*, email: str) -> None:
    """
    가입 인증 코드를 다시 보낸다.

    그 이메일로 진행 중인 가입이 없거나 발급 제한에 걸리면 아무 일도 하지 않는다.
    예외도 내지 않는다. 호출한 쪽이 경우를 구분할 수 없어야 한다.
    """
    user = _find_pending_user(email)
    if user is not None:
        _send_signup_code(user)


def delete_expired_pending_accounts() -> int:
    """보관 시간이 지난 미인증 계정을 모두 지우고, 지운 개수를 돌려준다."""
    deleted_count, _ = _expired_pending_accounts(timezone.now()).delete()
    return deleted_count


def authenticate_user(*, username: str, password: str) -> User:
    """
    아이디와 비밀번호가 맞는 사용자를 돌려준다.

    Django 의 authenticate 를 쓴다. 비밀번호 비교뿐 아니라 두 가지를 대신 해 준다.
      - 없는 아이디여도 해싱을 한 번 수행해, 응답 시간으로 가입 여부가 드러나지 않게 한다.
      - is_active 가 False 인 계정은 비밀번호가 맞아도 거부한다.
    """
    user = authenticate(username=username, password=password)
    if user is None:
        raise InvalidCredentialsError
    if not user.is_email_verified:
        raise EmailNotVerifiedError
    return user


def _find_verified_user(email: str) -> User | None:
    return User.objects.filter(email__iexact=email, email_verified_at__isnull=False).first()


def _find_pending_user(email: str) -> User | None:
    return User.objects.filter(email__iexact=email, email_verified_at__isnull=True).first()


def _expired_pending_accounts(now):
    return User.objects.filter(
        email_verified_at__isnull=True,
        date_joined__lt=now - PENDING_ACCOUNT_LIFETIME,
    )


def _delete_expired_pending_accounts(*, username: str, nickname: str, now) -> None:
    """
    이번 가입 요청과 아이디나 닉네임이 겹치는, 보관 시간이 지난 미인증 계정을 지운다.

    정리 명령이 돌지 않아도, 필요한 순간에 선점이 풀린다.
    """
    _expired_pending_accounts(now).filter(Q(username=username) | Q(nickname=nickname)).delete()


def _ensure_not_taken(*, username: str, nickname: str, email: str) -> None:
    """
    아이디와 닉네임을 다른 계정이 쓰고 있는지 본다.

    같은 이메일의 미인증 계정은 제외한다. 그 계정은 이번 요청으로 교체될 것이라
    자기 자신과 겹치는 것을 중복으로 보면 안 된다.
    """
    others = User.objects.exclude(email__iexact=email, email_verified_at__isnull=True)
    if others.filter(username=username).exists():
        raise FieldTakenError('username')
    if others.filter(nickname=nickname).exists():
        raise FieldTakenError('nickname')


def _save_pending_user(*, username: str, email: str, nickname: str, password_hash: str, now) -> User:
    """
    미인증 계정을 만든다. 같은 이메일의 미인증 계정이 있으면 그 행을 고쳐 쓴다.

    지우고 새로 만들지 않는다. 지우면 인증 코드의 발급 이력도 함께 사라져,
    가입 요청을 반복하는 것으로 발급 제한을 피해 남의 메일함에 코드를 계속 보낼 수 있다.
    """
    user = _find_pending_user(email) or User(email=email)
    user.username = username
    user.nickname = nickname
    user.password = password_hash
    # 보관 시간을 이번 요청부터 다시 센다
    user.date_joined = now
    user.save()
    return user


def _mark_email_verified(user: User) -> None:
    user.email_verified_at = timezone.now()
    user.save(update_fields=['email_verified_at'])


def _send_signup_code(user: User) -> None:
    """가입 인증 코드를 발급해 보낸다. 발급 제한에 걸리면 조용히 넘어간다."""
    try:
        code = issue_email_code(user=user, purpose=EmailCodePurpose.SIGNUP)
    except (EmailCodeCooldownError, EmailCodeLimitError):
        return
    send_email_code(user=user, purpose=EmailCodePurpose.SIGNUP, code=code)


def _send_already_registered_notice(user: User) -> None:
    """안내 메일을 보낸다. 인증 코드와 같은 발급 제한을 적용한다."""
    try:
        reserve_email_slot(user=user, purpose=EmailCodePurpose.SIGNUP)
    except (EmailCodeCooldownError, EmailCodeLimitError):
        return
    send_already_registered_notice(user=user)