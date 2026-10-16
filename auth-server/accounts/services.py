# auth-server/accounts/services.py

"""
accounts 앱의 도메인 로직.

HTTP 를 모른다. 요청과 응답 객체를 받지 않고, 검증이 끝난 값만 받는다.
그래서 뷰 없이도 테스트하고 다른 곳(관리 명령 등)에서 다시 쓸 수 있다.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.email_codes import (
    ISSUE_WINDOW,
    EmailCodeCooldownError,
    EmailCodeLimitError,
    InvalidEmailCodeError,
    consume_email_code,
    consume_email_token,
    consume_signup_code,
    has_usable_code,
    issue_email_code,
    issue_email_token,
    issue_signup_code,
    reserve_signup_slot,
)
from accounts.login_tickets import issue_login_ticket, read_login_ticket
from accounts.mail import (
    send_already_registered_notice,
    send_email_code,
    send_password_changed_notice,
    send_password_reset_link,
    send_signup_code,
)
from accounts.models import EmailCodePurpose, SignupCode, User
from accounts.signup_tickets import issue_signup_ticket, read_signup_ticket
from accounts.tokens import revoke_all_sessions
from accounts.welcome_credit import request_welcome_credit

# 가입 코드의 행을 남겨 두는 시간. 마지막 발급에서 발급 제한의 구간(1시간)이 지나면
# 쓸 수 있는 코드(5분)도 지킬 제한도 남지 않는다. 정리 명령이 그런 행을 지운다
STALE_SIGNUP_CODE_AGE = ISSUE_WINDOW

FIELD_TAKEN_MESSAGES = {
    'username': '이미 사용 중인 아이디입니다.',
    'nickname': '이미 사용 중인 닉네임입니다.',
}


class DuplicateAccountError(Exception):
    """아이디, 이메일, 닉네임 중 하나가 이미 쓰이고 있어 계정을 만들 수 없다. 사전 조회 뒤에 DB 가 막은 경우다."""


class EmailAlreadyRegisteredError(Exception):
    """
    가입 티켓의 이메일로 이미 계정이 있다. 같은 티켓을 두 번 쓴 경우다.

    티켓은 그 이메일의 코드를 맞힌 사람만 가지므로, 가입 여부를 알려 줘도 새는 것이 없다.
    """


class InvalidSignupFieldError(Exception):
    """가입 내용의 한 칸을 받아들일 수 없다. 어느 칸인지와 사람이 읽을 문장들을 담는다."""

    def __init__(self, field: str, messages: list[str]):
        super().__init__()
        self.field = field
        self.messages = messages


class FieldTakenError(InvalidSignupFieldError):
    """아이디나 닉네임을 다른 계정이 쓰고 있다. 이것은 숨기지 않는다. 다른 값을 골라야 하기 때문이다."""

    def __init__(self, field: str):
        super().__init__(field, [FIELD_TAKEN_MESSAGES[field]])


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


class LoginCodeUnavailableError(Exception):
    """
    로그인 코드를 지금은 보낼 수 없다. 발급 제한에 걸렸다.

    비밀번호를 통과한 사람에게만 낸다. 그래서 가입과 달리 숨기지 않고 사실대로 알린다.
    """

    def __init__(self, retry_after: timedelta):
        super().__init__()
        self.retry_after = retry_after


class WrongCurrentPasswordError(Exception):
    """비밀번호를 바꾸려는데 현재 비밀번호가 틀렸다."""


class UnacceptablePasswordError(Exception):
    """새 비밀번호가 규칙에 맞지 않는다. 이유를 사람이 읽을 문장으로 담는다."""

    def __init__(self, messages: list[str]):
        super().__init__()
        self.messages = messages


@dataclass(frozen=True)
class LoginChallenge:
    """비밀번호 확인을 통과한 뒤 다음 단계로 넘기는 것."""

    ticket: str
    # False 면 새 코드를 보내지 않았다. 직전에 보낸 코드가 아직 유효하다
    code_sent: bool


def start_signup(*, email: str) -> None:
    """
    가입의 1단계. 그 이메일로 코드를 보낸다. 이미 가입된 주소면 코드 대신 안내 메일을 보낸다.

    두 경우 모두 아무것도 돌려주지 않는다. 호출한 쪽이 둘을 구분할 수 없어야
    응답으로 이메일의 가입 여부가 드러나지 않는다. 두 메일은 같은 발급 제한(그 이메일의 행)을 쓴다.
    발급 제한에 걸리면 조용히 넘어간다. 다시 보내기도 이 함수다.

    계정은 만들지 않는다. 아이디와 비밀번호는 코드를 맞힌 뒤에 정한다(complete_signup).
    그래서 이메일의 주인이 아닌 사람은 그 이메일의 가입 내용을 정할 수 없다(#271).
    """
    registered_user = _find_user_by_email(email)
    if registered_user is None:
        _send_signup_code(email)
    else:
        _send_already_registered_notice(email, registered_user)


def verify_signup(*, email: str, code: str) -> str:
    """
    가입의 2단계. 코드를 확인하고, 맞으면 3단계에 쓸 가입 티켓을 돌려준다.

    코드가 틀렸거나, 그 이메일로 보낸 코드가 없으면(이미 가입된 주소 포함) InvalidEmailCodeError 를 낸다.
    두 경우를 구분하지 않는다. 틀린 횟수는 로그인 코드처럼 세고, 다섯 번 틀리면 코드가 폐기된다.
    """
    consume_signup_code(email=email, code=code)
    # 코드 소비가 커밋된 뒤에 만든다. 티켓은 DB 에 적지 않는다
    return issue_signup_ticket(email)


def complete_signup(*, signup_ticket: str, username: str, nickname: str, password: str) -> User:
    """
    가입의 3단계. 티켓의 이메일로 인증된 계정을 만들고, 환영 크레딧을 주라고 적어 둔다.

    티켓이 틀렸거나 만료됐으면 InvalidSignupTicketError, 아이디나 비밀번호가 규칙에 맞지 않거나
    아이디나 닉네임을 다른 계정이 쓰면 InvalidSignupFieldError, 이미 그 이메일로 가입했으면
    EmailAlreadyRegisteredError, 사전 조회 뒤에 다른 요청이 먼저 저장했으면 DuplicateAccountError 를 낸다.
    """
    email = read_signup_ticket(signup_ticket)
    _check_username_differs_from_email(username=username, email=email)
    _check_password_strength(username=username, email=email, nickname=nickname, password=password)
    _ensure_email_free(email)
    _ensure_not_taken(username=username, nickname=nickname)

    try:
        # 계정 저장과 환영 크레딧 적기가 한 트랜잭션이다.
        # 가입은 됐는데 크레딧을 줄 일은 적히지 않은 경우가 생기지 않는다
        with transaction.atomic():
            user = _create_verified_user(username=username, email=email, nickname=nickname, password=password)
            request_welcome_credit(user)
    except IntegrityError as exc:
        # 사전 조회를 통과한 뒤 다른 요청이 같은 값으로 먼저 저장한 경우.
        # 같은 티켓을 동시에 두 번 보낸 것도 여기다(이메일의 유일 제약)
        raise DuplicateAccountError from exc
    return user


def delete_stale_signup_codes() -> int:
    """마지막 발급에서 발급 제한의 구간이 지난 가입 코드의 행을 지우고, 지운 개수를 돌려준다."""
    cutoff = timezone.now() - STALE_SIGNUP_CODE_AGE
    deleted_count, _ = SignupCode.objects.filter(last_issued_at__lt=cutoff).delete()
    return deleted_count


def start_login(*, username: str, password: str) -> LoginChallenge:
    """
    로그인의 1단계. 아이디와 비밀번호를 확인하고 이메일로 인증 코드를 보낸다.

    토큰은 아직 주지 않는다. 2단계에서 쓸 티켓만 돌려준다.
    비밀번호가 틀리면 InvalidCredentialsError, 코드를 보낼 수 없으면 LoginCodeUnavailableError 를 낸다.
    """
    user = authenticate_user(username=username, password=password)
    code_sent = _send_login_code(user)
    return LoginChallenge(ticket=issue_login_ticket(user), code_sent=code_sent)


def complete_login(*, login_ticket: str, code: str) -> User:
    """
    로그인의 2단계. 티켓과 인증 코드를 확인하고 로그인한 사용자를 돌려준다.

    티켓을 쓸 수 없으면 InvalidLoginTicketError, 코드가 틀리면 InvalidEmailCodeError 를 낸다.
    """
    user = read_login_ticket(login_ticket)
    consume_email_code(user=user, purpose=EmailCodePurpose.LOGIN, code=code)
    return user


def resend_login_code(*, login_ticket: str) -> None:
    """
    로그인 인증 코드를 다시 보낸다. 전에 보낸 코드는 못 쓰게 된다.

    발급 제한에 걸리면 LoginCodeUnavailableError 를 낸다.
    """
    user = read_login_ticket(login_ticket)
    try:
        _issue_and_send_code(user, EmailCodePurpose.LOGIN)
    except (EmailCodeCooldownError, EmailCodeLimitError) as exc:
        raise LoginCodeUnavailableError(exc.retry_after) from exc


def change_password(*, user: User, current_password: str, new_password: str) -> None:
    """
    로그인한 사용자의 비밀번호를 바꾸고, 발급돼 있던 토큰을 전부 무효로 만든다.

    현재 비밀번호를 다시 확인한다. access 토큰만으로 바꿀 수 있으면,
    자리를 비운 사이 열려 있는 화면에서 남이 바꿀 수 있다.
    호출한 쪽이 이 기기에 새 토큰을 발급해야 한다. 그러지 않으면 이 기기도 로그아웃된다.
    """
    if not user.check_password(current_password):
        raise WrongCurrentPasswordError
    if current_password == new_password:
        raise UnacceptablePasswordError(['새 비밀번호는 현재 비밀번호와 달라야 합니다.'])

    with transaction.atomic():
        _set_new_password(user, new_password)


def request_password_reset(*, email: str) -> None:
    """
    비밀번호 재설정 링크를 메일로 보낸다.

    가입된 주소가 아니거나 발급 제한에 걸리면 아무 일도 하지 않는다. 예외도 내지 않는다.
    호출한 쪽이 경우를 구분할 수 없어야 이메일의 가입 여부가 드러나지 않는다.
    """
    user = _find_verified_user(email)
    if user is None or not user.is_active:
        return

    try:
        # 토큰 발급과 보낼 메일 적기가 한 트랜잭션이다
        with transaction.atomic():
            token = issue_email_token(user=user, purpose=EmailCodePurpose.PASSWORD_RESET)
            send_password_reset_link(user=user, token=token)
    except (EmailCodeCooldownError, EmailCodeLimitError):
        return


def reset_password(*, email: str, token: str, new_password: str) -> None:
    """
    재설정 토큰을 확인하고 새 비밀번호로 바꾼다. 모든 기기에서 로그아웃된다.

    토큰이 틀렸거나 그런 계정이 없으면 InvalidEmailCodeError 를 낸다. 둘을 구분하지 않는다.
    새 비밀번호가 규칙에 맞지 않으면 UnacceptablePasswordError 를 내고, 토큰은 쓰이지 않은 채로 남는다.
    """
    user = _find_verified_user(email)
    if user is None or not user.is_active:
        raise InvalidEmailCodeError

    consume_email_token(
        user=user,
        purpose=EmailCodePurpose.PASSWORD_RESET,
        token=token,
        # 토큰 소비, 비밀번호 저장, 세션 종료, 알림 메일 적기가 한 트랜잭션이다.
        # 비밀번호 규칙 검사도 여기서 한다. 토큰이 맞은 뒤에만 실행되므로,
        # "이 비밀번호는 이 계정의 아이디와 비슷하다" 같은 답이 토큰을 가진 사람에게만 간다
        on_success=lambda: _set_new_password(user, new_password),
    )


def spend_password_check_time(*, password: str) -> None:
    """
    비밀번호를 확인할 때만큼의 시간을 쓴다. 결과는 버린다.

    확인도 하지 않고 거절하는 요청(막힌 IP 의 로그인)에 쓴다.
    바로 응답하면 평소의 거절보다 훨씬 빨라서, 응답 시간으로 막혔다는 것이 드러난다.
    """
    make_password(password)


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


def _find_user_by_email(email: str) -> User | None:
    """
    그 이메일의 계정. 인증했는지는 보지 않는다.

    가입이 인증된 계정만 만들므로 미인증 계정은 관리자가 손으로 만든 것뿐이다. 그래도 그 이메일은 쓰이고 있다.
    """
    return User.objects.filter(email__iexact=email).first()


def _check_username_differs_from_email(*, username: str, email: str) -> None:
    """
    아이디가 이메일의 @ 앞부분과 같으면 거부한다.

    같으면 아이디를 아는 사람이 이메일을 추측할 수 있어 둘을 분리한 의미가 줄어든다.
    """
    if username == email.split('@')[0]:
        raise InvalidSignupFieldError('username', ['아이디는 이메일의 @ 앞부분과 달라야 합니다.'])


def _check_password_strength(*, username: str, email: str, nickname: str, password: str) -> None:
    """
    settings 의 AUTH_PASSWORD_VALIDATORS 로 비밀번호를 검사한다.

    "아이디와 비슷한 비밀번호" 를 걸러내려면 검증기가 아이디를 알아야 한다.
    저장하지 않는 임시 User 객체에 값을 담아 넘긴다.
    """
    candidate = User(username=username, email=email, nickname=nickname)
    try:
        validate_password(password, user=candidate)
    except ValidationError as exc:
        raise InvalidSignupFieldError('password', list(exc.messages)) from exc


def _ensure_email_free(email: str) -> None:
    if _find_user_by_email(email) is not None:
        raise EmailAlreadyRegisteredError


def _ensure_not_taken(*, username: str, nickname: str) -> None:
    """아이디와 닉네임을 다른 계정이 쓰고 있는지 본다."""
    if User.objects.filter(username=username).exists():
        raise FieldTakenError('username')
    if User.objects.filter(nickname=nickname).exists():
        raise FieldTakenError('nickname')


def _create_verified_user(*, username: str, email: str, nickname: str, password: str) -> User:
    """
    인증된 계정을 만든다. 이메일은 가입 티켓이 증명한 것이라 바로 인증된 것으로 적는다.

    권한(is_staff, is_superuser)은 기본값 그대로다. 요청 본문에서 오는 값이 아니다.
    """
    user = User(username=username, email=email, nickname=nickname, email_verified_at=timezone.now())
    user.set_password(password)
    user.save()
    return user


def _set_new_password(user: User, new_password: str) -> None:
    """
    새 비밀번호를 검사해 저장하고, 발급돼 있던 토큰을 전부 무효로 만들고, 알림 메일을 맡긴다.

    트랜잭션 안에서 불러야 한다. 비밀번호만 바뀌고 옛 세션이 살아남거나,
    비밀번호는 바뀌었는데 알림이 빠지는 일이 없어야 한다.
    """
    try:
        # 아이디, 이메일, 닉네임과 비슷한 비밀번호를 걸러내려면 검증기가 사용자를 알아야 한다
        validate_password(new_password, user=user)
    except ValidationError as exc:
        raise UnacceptablePasswordError(list(exc.messages)) from exc

    user.set_password(new_password)
    user.save(update_fields=['password'])
    revoke_all_sessions(user)
    send_password_changed_notice(user=user)


def _send_signup_code(email: str) -> None:
    """
    가입 코드를 발급하고 그 코드를 담은 메일을 발송함에 적는다. 둘이 한 트랜잭션이다.

    발급 제한에 걸리면 조용히 넘어간다.
    """
    try:
        with transaction.atomic():
            code = issue_signup_code(email=email)
            send_signup_code(email=email, code=code)
    except (EmailCodeCooldownError, EmailCodeLimitError):
        return


def _send_already_registered_notice(email: str, user: User) -> None:
    """안내 메일을 보낸다. 가입 코드와 같은 발급 제한(그 이메일의 행)을 적용한다."""
    try:
        with transaction.atomic():
            reserve_signup_slot(email=email)
            send_already_registered_notice(user=user)
    except (EmailCodeCooldownError, EmailCodeLimitError):
        return


def _send_login_code(user: User) -> bool:
    """
    로그인 인증 코드를 발급해 보낸다. 새 코드를 보냈으면 True 를 돌려준다.

    직전 발급에서 1분이 지나지 않았더라도, 그때 보낸 코드가 아직 유효하면 그것을 쓰면 된다.
    그 경우 False 를 돌려준다. 쓸 코드도 없고 새로 보낼 수도 없으면 예외를 낸다.
    """
    try:
        _issue_and_send_code(user, EmailCodePurpose.LOGIN)
    except EmailCodeCooldownError as exc:
        if has_usable_code(user=user, purpose=EmailCodePurpose.LOGIN):
            return False
        raise LoginCodeUnavailableError(exc.retry_after) from exc
    except EmailCodeLimitError as exc:
        raise LoginCodeUnavailableError(exc.retry_after) from exc
    return True


def _issue_and_send_code(user: User, purpose: str) -> None:
    """
    인증 코드를 발급하고 그 코드를 담은 메일을 발송함에 적는다. 둘이 한 트랜잭션이다.

    따로 하면 "코드는 발급됐는데 보낼 메일은 적히지 않은" 순간이 생긴다.
    그때는 사용자가 받지 못한 코드 때문에 1분을 기다려야 한다.
    발급 제한에 걸리면 EmailCodeCooldownError 나 EmailCodeLimitError 가 그대로 올라간다.
    """
    with transaction.atomic():
        code = issue_email_code(user=user, purpose=purpose)
        send_email_code(user=user, purpose=purpose, code=code)
