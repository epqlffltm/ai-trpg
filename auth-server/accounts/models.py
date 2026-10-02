# auth-server/accounts/models.py

"""
인증 서버의 User 모델.

Django 기본 User 를 그대로 쓰지 않고 AbstractUser 를 상속해 필요한 부분만 바꾼다.
비밀번호 해싱, 권한, 관리자 화면 연동은 Django 가 제공하는 것을 그대로 쓴다.
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from accounts.validators import (
    NICKNAME_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
    validate_nickname_format,
    validate_username_format,
    validate_username_not_reserved,
)


class User(AbstractUser):
    # 로그인 ID. 이메일과 분리한다.
    # AbstractUser 의 username 은 @ 와 . 을 허용하므로 같은 이름으로 다시 정의해 규칙을 바꾼다
    username = models.CharField(
        '아이디',
        max_length=USERNAME_MAX_LENGTH,
        unique=True,
        validators=[validate_username_format, validate_username_not_reserved],
        error_messages={'unique': '이미 사용 중인 아이디입니다.'},
    )

    # 인증 코드를 받는 주소. 로그인 식별자로는 쓰지 않는다.
    # 중복 검사는 아래 Meta.constraints 에서 대소문자를 무시하고 한다
    email = models.EmailField('이메일')

    # 다른 사용자에게 보이는 이름
        # 다른 사용자에게 보이는 이름
    nickname = models.CharField(
        '닉네임',
        max_length=NICKNAME_MAX_LENGTH,
        unique=True,
        validators=[validate_nickname_format],
        error_messages={'unique': '이미 사용 중인 닉네임입니다.'},
    )
    # 외부에 내보내는 식별자. JWT 의 sub 와 API 응답에 쓴다.
    # 정수 PK 를 노출하면 가입자 수와 가입 순서를 추측할 수 있다.
    # 정수 PK 는 내부 조인용으로 그대로 둔다
    public_id = models.UUIDField(
        '공개 ID',
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    
    # 세션 버전. 토큰에 이 값을 넣어 발급하고, 검증할 때 현재 값과 비교한다.
    # 값을 올리면 그 전에 발급된 토큰이 전부 무효가 된다.
    # 비밀번호를 바꿨을 때나 토큰 탈취가 의심될 때 올린다
    token_version = models.PositiveIntegerField('세션 버전', default=0)

    # AbstractUser 가 가진 실명 필드를 없앤다. 수집하지 않는 정보의 컬럼은 두지 않는다
    first_name = None
    last_name = None

    # createsuperuser 가 아이디와 비밀번호 외에 추가로 묻는 필드
    REQUIRED_FIELDS = ['email', 'nickname']

    class Meta:
        verbose_name = '회원'
        verbose_name_plural = '회원'
        constraints = [
            # A@x.com 과 a@x.com 을 같은 주소로 본다.
            # 코드가 아니라 DB 가 막으므로 어느 경로로 저장해도 중복이 생기지 않는다
            models.UniqueConstraint(
                Lower('email'),
                name='accounts_user_email_ci_unique',
                violation_error_message='이미 사용 중인 이메일입니다.',
            ),
        ]

    def __str__(self) -> str:
        return self.username

    @classmethod
    def normalize_username(cls, username):
        """아이디를 소문자로 통일한다. create_user 와 createsuperuser 가 저장 전에 호출한다."""
        return super().normalize_username(username).lower()

    def get_full_name(self) -> str:
        """실명 필드가 없으므로 닉네임을 돌려준다. 관리자 화면이 이 메서드를 호출한다."""
        return self.nickname

    def get_short_name(self) -> str:
        return self.nickname