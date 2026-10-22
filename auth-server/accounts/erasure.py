# auth-server/accounts/erasure.py

"""
계정을 비우는 일. 만 14세 미만으로 막은 계정(identity.py)과 탈퇴를 마친 계정(withdrawal.py)이 함께 쓴다.

계정의 줄은 지우지 않는다. 지우면 세션 버전이 함께 사라져 다른 서버가 끊긴 세션을 알 길이 없고,
공개 ID 가 사라져 다른 서버가 그 사람의 것을 가려 지울 수 없다. 그래서 줄을 남기고 사람을 알아볼 수 있는 칸을 비운다.
이 모듈의 함수는 부르는 쪽이 계정의 줄을 잠근 트랜잭션 안에서 부른다.
"""

from django.contrib.auth.hashers import make_password

from accounts.models import (
    EmailCode,
    GuardianConsent,
    IdentityVerification,
    OutgoingMail,
    PaymentEligibility,
    SignupCode,
    Suspension,
    User,
)

# 비운 계정의 이름과 주소. 줄 번호를 붙여 겹치지 않게 한다.
# 붙임표(-)는 아이디와 닉네임의 규칙(validators.py)이 받지 않는 글자다. 사용자가 먼저 가져갈 수 없다.
# .invalid 는 메일이 닿지 않는 이름이다(RFC 2606). 같은 주소로 가입할 수 없다
REMOVED_NAME = 'removed-{pk}'
REMOVED_EMAIL = '{pk}@removed.invalid'


def is_removed_account(user: User) -> bool:
    """비운 계정인가(만 14세 미만이나 탈퇴). 닉네임이 REMOVED_NAME 이다(사용자가 고를 수 없는 이름)."""
    return user.nickname == REMOVED_NAME.format(pk=user.pk)


def blank_account(user: User) -> None:
    """계정을 막고 아이디, 닉네임, 이메일, 비밀번호를 비운다."""
    user.is_active = False
    user.username = REMOVED_NAME.format(pk=user.pk)
    user.nickname = REMOVED_NAME.format(pk=user.pk)
    user.email = REMOVED_EMAIL.format(pk=user.pk)
    # 쓸 수 없는 비밀번호. 비밀번호의 해시도 그 사람이 고른 것에서 나온 값이다
    user.password = make_password(None)
    user.save(update_fields=['is_active', 'username', 'nickname', 'email', 'password'])


def erase_mail_records(user: User, email: str) -> None:
    """그 계정과 주소로 남은 코드와 보낼 메일을 지운다. 주소가 그대로 적힌 줄들이다."""
    EmailCode.objects.filter(user=user).delete()
    SignupCode.objects.filter(email=email.lower()).delete()
    OutgoingMail.objects.filter(to_email__iexact=email).delete()


def erase_suspensions(user: User) -> None:
    """
    정지의 기록을 지운다(#634). 운영자가 적은 사유는 그 사람에 관한 글이다.

    정지된 채 탈퇴하는 사람의 재가입을 막는 데 필요한 것(사유의 종류)은 부르는 쪽이 지우기 전에 읽는다.
    """
    Suspension.objects.filter(user=user).delete()


def erase_identity_records(user: User) -> None:
    """
    본인인증과 그에 딸린 기록을 지운다. 사람의 구별 값, 미성년자의 날짜, 보호자의 이메일, 결제 자격의 알림이다.

    결제 서버가 받아 둔 결제 자격은 결제 서버가 지운다(탈퇴 알림). 여기서는 이 서버의 줄만 지운다.
    환영 크레딧을 받은 사람의 구별 값(WelcomeCredit)은 지우지 않는다. 같은 사람이 계정을 바꿔 다시 받지 못하게 한다.
    """
    IdentityVerification.objects.filter(user=user).delete()
    GuardianConsent.objects.filter(minor=user).delete()
    PaymentEligibility.objects.filter(user=user).delete()
