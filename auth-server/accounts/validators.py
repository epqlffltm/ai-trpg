# auth-server/accounts/validators.py

"""
accounts 앱의 필드 검증기.

검증기는 값 하나를 받아, 규칙에 어긋나면 ValidationError 를 던진다.
모델 필드에 붙이면 관리자 화면과 API 양쪽에서 같은 규칙이 적용된다.
"""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from accounts.reserved import is_reserved_name

USERNAME_MIN_LENGTH = 4
USERNAME_MAX_LENGTH = 20

NICKNAME_MIN_LENGTH = 2
NICKNAME_MAX_LENGTH = 20

# 영문 소문자, 숫자, 밑줄만 허용한다.
# @ 와 . 을 막아 이메일 주소를 아이디로 쓰지 못하게 한다.
# 끝을 $ 가 아니라 \Z 로 잡는다. $ 는 맨 끝의 줄바꿈 문자를 통과시킨다
validate_username_format = RegexValidator(
    regex=rf'\A[a-z0-9_]{{{USERNAME_MIN_LENGTH},{USERNAME_MAX_LENGTH}}}\Z',
    message=(
        f'아이디는 영문 소문자, 숫자, 밑줄만 쓸 수 있고 '
        f'{USERNAME_MIN_LENGTH}자 이상 {USERNAME_MAX_LENGTH}자 이하여야 합니다.'
    ),
    code='invalid_username',
)


def validate_username_not_reserved(username: str) -> None:
    """예약어를 아이디로 쓰지 못하게 한다."""
    if is_reserved_name(username):
        raise ValidationError(
            '사용할 수 없는 아이디입니다.',
            code='reserved_username',
        )

# 한글, 영문, 숫자, 밑줄만 허용한다.
# 공백을 막아 "운영자 " 나 "운 영 자" 처럼 예약어 검사를 피해 가는 이름을 쓰지 못하게 한다
validate_nickname_format = RegexValidator(
    regex=rf'\A[가-힣a-zA-Z0-9_]{{{NICKNAME_MIN_LENGTH},{NICKNAME_MAX_LENGTH}}}\Z',
    message=(
        f'닉네임은 한글, 영문, 숫자, 밑줄만 쓸 수 있고 '
        f'{NICKNAME_MIN_LENGTH}자 이상 {NICKNAME_MAX_LENGTH}자 이하여야 합니다.'
    ),
    code='invalid_nickname',
)


def validate_nickname_not_reserved(nickname: str) -> None:
    """
    예약어를 닉네임으로 쓰지 못하게 한다.

    모델 필드에는 붙이지 않는다. 운영자 본인은 관리자 화면에서 이런 닉네임을 쓸 수 있어야 한다.
    일반 회원이 거치는 회원가입 API 에서만 쓴다.
    """
    if is_reserved_name(nickname):
        raise ValidationError(
            '사용할 수 없는 닉네임입니다.',
            code='reserved_nickname',
        )