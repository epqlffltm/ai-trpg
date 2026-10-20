# auth-server/accounts/identity.py

"""
휴대폰 본인인증(#336). 로그인한 사용자가 본인확인 업체에서 받은 token 을 내면, 업체에 물어 결과를 적는다.

  1. 이미 인증한 계정이면 거절한다. 인증은 계정마다 한 번이다
  2. 업체에 묻는다(identity_providers.py). 트랜잭션 밖에서 한다. 업체가 느려도 DB 의 잠금을 오래 쥐지 않는다
  3. 만 14세 미만이면 계정을 막고 모은 개인정보를 지운다. 개인정보 보호법(22조의2)은 만 14세 미만의
     개인정보를 보호자의 동의 없이 모으지 못하게 한다. 이 서비스는 보호자 동의를 받아 가입시키지 않는다
  4. 다른 계정이 이미 인증한 사람이면 거절한다. 한 사람은 한 계정에서만 인증한다
  5. 인증 기록과 환영 크레딧, 결제 서버에 알릴 결제 자격을 한 트랜잭션에서 적는다

결과는 바로 토큰에 실리지 않는다. 다음에 토큰을 갱신할 때 실린다(tokens.py). 화면은 인증 뒤에 갱신을 부른다.
"""

from datetime import date

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from accounts.age import adult_content_from, has_reached, is_under_min_age, korean_today, legal_adult_from
from accounts.consents import erase_consents
from accounts.identity_providers import IdentityResult, get_identity_provider
from accounts.models import (
    EmailCode,
    IdentityVerification,
    OutgoingMail,
    SecurityEventKind,
    SignupCode,
    User,
)
from accounts.payment_eligibility import mark_changed
from accounts.security_events import record_security_event
from accounts.tokens import revoke_all_sessions
from accounts.welcome_credit import request_welcome_credit

# 사람 열쇠를 만들 때 SECRET_KEY 에 섞는 값.
# 같은 SECRET_KEY 에서 나온 다른 용도의 값(인증 코드 해시, 옛 메일함의 열쇠)과 겹치지 않게 한다
PERSON_KEY_SALT = 'accounts.identity.person'

# 만 14세 미만으로 막은 계정의 이름과 주소. 줄 번호를 붙여 겹치지 않게 한다.
# 붙임표(-)는 아이디와 닉네임의 규칙(validators.py)이 받지 않는 글자다. 사용자가 먼저 가져갈 수 없다.
# .invalid 는 메일이 닿지 않는 이름이다(RFC 2606). 같은 주소로 가입할 수 없다
REMOVED_NAME = 'removed-{pk}'
REMOVED_EMAIL = '{pk}@removed.invalid'


class IdentityAlreadyVerifiedError(Exception):
    """이 계정은 이미 본인인증을 했다."""


class IdentityInUseError(Exception):
    """다른 계정이 이미 이 사람으로 인증했다."""


class UnderMinAgeError(Exception):
    """만 14세 미만이다. 계정을 막고 개인정보를 지웠다."""


def person_key(di: str) -> str:
    """
    사람 열쇠. 업체가 준 DI 를 서버의 비밀키로 서명한 값이다(HMAC-SHA256, 16진수 64자).

    SECRET_KEY 를 바꾸면 열쇠가 모두 달라진다. 그 전에 인증한 사람이 다른 계정에서 다시 인증할 수 있고,
    환영 크레딧을 다시 받을 수 있게 된다. SECRET_KEY 는 바꾸지 않는 값으로 다룬다.
    """
    return salted_hmac(PERSON_KEY_SALT, di, algorithm='sha256').hexdigest()


def verify_identity(*, user: User, token: str, ip: str = '') -> IdentityVerification:
    """
    본인인증을 하고 기록을 돌려준다. ip 는 다른 계정의 사람일 때 보안 이벤트에 남긴다.

    이미 인증했으면 IdentityAlreadyVerifiedError, 업체가 token 을 모르면 IdentityTokenError,
    업체를 쓸 수 없으면 IdentityUnavailableError, 만 14세 미만이면 UnderMinAgeError,
    다른 계정의 사람이면 IdentityInUseError 를 낸다.
    """
    _ensure_not_verified(user)
    provider = get_identity_provider()
    result = provider.verify(token)
    today = korean_today()

    if is_under_min_age(result.birth_date, today):
        close_under_age_account(user)
        raise UnderMinAgeError

    try:
        return _record_verification(user, result, provider.name, today)
    except IdentityInUseError:
        # 위의 트랜잭션은 취소됐다. 이벤트는 따로 남긴다
        record_security_event(kind=SecurityEventKind.IDENTITY_IN_USE, user=user, ip=ip)
        raise


def _ensure_not_verified(user: User) -> None:
    """이미 인증한 계정이면 업체에 묻기 전에 거절한다. token 을 헛되이 쓰지 않는다."""
    if IdentityVerification.objects.filter(user=user).exists():
        raise IdentityAlreadyVerifiedError


@transaction.atomic
def _record_verification(user: User, result: IdentityResult, provider_name: str, today: date) -> IdentityVerification:
    """
    인증 기록과 환영 크레딧, 결제 자격을 한 트랜잭션에서 적는다.

    계정의 줄을 잠근다. 같은 계정의 요청 둘이 함께 와도 하나만 적힌다. 그래서 남는 유일 제약 위반은
    사람 열쇠뿐이다. 다른 계정이 먼저 그 사람으로 인증했다.
    """
    locked = _lock(user)
    _ensure_not_verified(locked)
    key = person_key(result.di)
    try:
        verification = IdentityVerification.objects.create(
            user=locked,
            person_key=key,
            legal_adult_from=_future_or_none(legal_adult_from(result.birth_date), today),
            adult_content_from=_future_or_none(adult_content_from(result.birth_date), today),
            provider=provider_name,
            verified_at=timezone.now(),
        )
    except IntegrityError as exc:
        # 트랜잭션 전체가 취소된다. 환영 크레딧도 적히지 않는다
        raise IdentityInUseError from exc
    request_welcome_credit(user_public_id=locked.public_id, recipient_key=key)
    # 결제 서버가 이 사용자의 나이(성년이 되는 날)를 알게 한다. 결제는 그것으로 가른다(#337)
    mark_changed(locked)
    return verification


def _future_or_none(day: date, today: date) -> date | None:
    """그날이 아직 오지 않았으면 그날을, 이미 왔으면 None 을 돌려준다. 성인의 생일을 남기지 않는다."""
    if has_reached(day, today):
        return None
    return day


@transaction.atomic
def close_under_age_account(user: User) -> None:
    """
    만 14세 미만의 계정을 막고, 모은 개인정보를 지운다.

    계정의 줄은 지우지 않는다. 지우면 세션 버전이 함께 사라져, 다른 서버가 끊긴 세션을 알 길이 없다.
    이미 발급된 access 토큰이 만료(15분)까지 통한다. 그래서 정지처럼 막고 세션을 끊은 뒤 내용을 비운다.
    공개 ID 는 남는다. 다른 서버가 그 사용자의 것을 가려 지울 때 쓴다.
    가입 때 받은 동의의 기록도 지운다(#450). 그 나이의 본인 동의는 쓸 수 없다.
    보안 이벤트에 남은 IP 는 지우지 않는다. 보관 기간이 지나면 함께 지워진다(security_digest.py).
    """
    locked = _lock(user)
    email = locked.email
    _blank_account(locked)
    revoke_all_sessions(locked)
    _erase_mail_records(locked, email)
    erase_consents(locked)
    record_security_event(kind=SecurityEventKind.IDENTITY_UNDER_AGE, user=locked)


def _lock(user: User) -> User:
    """계정의 줄을 잠그고 지금 값으로 다시 읽는다."""
    return User.objects.select_for_update().get(pk=user.pk)


def _blank_account(user: User) -> None:
    """계정을 막고 아이디, 닉네임, 이메일, 비밀번호를 비운다."""
    user.is_active = False
    user.username = REMOVED_NAME.format(pk=user.pk)
    user.nickname = REMOVED_NAME.format(pk=user.pk)
    user.email = REMOVED_EMAIL.format(pk=user.pk)
    # 쓸 수 없는 비밀번호. 비밀번호의 해시도 그 사람이 고른 것에서 나온 값이다
    user.password = make_password(None)
    user.save(update_fields=['is_active', 'username', 'nickname', 'email', 'password'])


def _erase_mail_records(user: User, email: str) -> None:
    """그 계정과 주소로 남은 코드와 보낼 메일을 지운다. 주소가 그대로 적힌 줄들이다."""
    EmailCode.objects.filter(user=user).delete()
    SignupCode.objects.filter(email=email.lower()).delete()
    OutgoingMail.objects.filter(to_email__iexact=email).delete()
