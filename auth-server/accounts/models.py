# auth-server/accounts/models.py

"""
인증 서버의 User 모델.

Django 기본 User 를 그대로 쓰지 않고 AbstractUser 를 상속해 필요한 부분만 바꾼다.
비밀번호 해싱, 권한, 관리자 화면 연동은 Django 가 제공하는 것을 그대로 쓴다.
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from accounts.validators import (
    NICKNAME_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
    validate_nickname_format,
    validate_username_format,
    validate_username_not_reserved,
)

class UserManager(DjangoUserManager):
    """User 를 만드는 방법을 모아 둔 매니저."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """
        관리자 계정은 만들 때부터 이메일이 인증된 것으로 둔다.

        createsuperuser 는 서버에 직접 접근할 수 있는 사람만 실행한다.
        인증 메일을 거치게 하면 메일 설정이 없는 환경에서 첫 관리자를 만들 수 없다.
        """
        extra_fields.setdefault('email_verified_at', timezone.now())
        return super().create_superuser(username, email, password, **extra_fields)

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
    
    # 이메일 주소의 주인임을 확인한 시각. 비어 있으면 아직 인증하지 않은 계정이다.
    # 참/거짓 대신 시각을 저장한다. 언제 인증했는지도 함께 남는다
    email_verified_at = models.DateTimeField('이메일 인증 시각', null=True, blank=True)
    
    # 세션 버전. 토큰에 이 값을 넣어 발급하고, 검증할 때 현재 값과 비교한다.
    # 값을 올리면 그 전에 발급된 토큰이 전부 무효가 된다.
    # 비밀번호를 바꿨을 때나 토큰 탈취가 의심될 때 올린다
    token_version = models.PositiveIntegerField('세션 버전', default=0)

    # AbstractUser 가 가진 실명 필드를 없앤다. 수집하지 않는 정보의 컬럼은 두지 않는다
    first_name = None
    last_name = None

    # createsuperuser 가 아이디와 비밀번호 외에 추가로 묻는 필드
    REQUIRED_FIELDS = ['email', 'nickname']

    objects = UserManager()
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
    
    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    @classmethod
    def normalize_username(cls, username):
        """아이디를 소문자로 통일한다. create_user 와 createsuperuser 가 저장 전에 호출한다."""
        return super().normalize_username(username).lower()

    def get_full_name(self) -> str:
        """실명 필드가 없으므로 닉네임을 돌려준다. 관리자 화면이 이 메서드를 호출한다."""
        return self.nickname

    def get_short_name(self) -> str:
        return self.nickname
    
class EmailCodePurpose(models.TextChoices):
    """
    인증 코드의 용도.

    코드는 발급받은 용도로만 쓸 수 있다. 용도를 구분하지 않으면
    가입 인증용으로 받은 코드로 비밀번호를 바꿀 수 있게 된다.
    """

    SIGNUP = 'signup', '가입 인증'
    LOGIN = 'login', '로그인 인증'
    PASSWORD_RESET = 'password_reset', '비밀번호 재설정'


class EmailCode(models.Model):
    """
    이메일로 보낸 인증 코드와 그 발급 이력.

    회원과 용도마다 행이 하나뿐이다. 새 코드를 발급하면 행을 새로 만들지 않고 덮어쓴다.
    그래서 테이블이 계속 불어나지 않고, 만료된 코드를 따로 지울 필요가 없다.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='email_codes',
        verbose_name='회원',
    )
    purpose = models.CharField('용도', max_length=20, choices=EmailCodePurpose.choices)

    # 코드의 원문은 저장하지 않는다. 비교만 하면 되는 값이라 해시로 충분하다.
    # 빈 문자열이면 쓸 수 있는 코드가 없다는 뜻이다(이미 썼거나 폐기됐다)
    code_hash = models.CharField('코드 해시', max_length=64, blank=True)
    expires_at = models.DateTimeField('만료 시각')
    failed_attempts = models.PositiveSmallIntegerField('틀린 횟수', default=0)

    # 발급 횟수 제한에 쓴다
    last_issued_at = models.DateTimeField('마지막 발급 시각')
    window_started_at = models.DateTimeField('발급 횟수를 세기 시작한 시각')
    issued_in_window = models.PositiveSmallIntegerField('구간 안의 발급 횟수', default=0)

    class Meta:
        verbose_name = '인증 코드'
        verbose_name_plural = '인증 코드'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'purpose'],
                name='accounts_emailcode_user_purpose_unique',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.user} / {self.get_purpose_display()}'