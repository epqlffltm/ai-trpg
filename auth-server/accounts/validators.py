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