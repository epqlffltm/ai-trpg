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


class SecurityEventKind(models.TextChoices):
    LOGIN_IP_LIMITED = 'login_ip_limited', '로그인: IP 시도 제한'
    LOGIN_FAILURES_LIMITED = 'login_failures_limited', '로그인: 비밀번호 틀림 제한'
    RESERVED_USERNAME_LOGIN = 'reserved_username_login', '로그인: 예약어 아이디로 시도해 IP 차단'
    SIGNUP_IP_LIMITED = 'signup_ip_limited', '가입: IP 시도 제한'
    SIGNUP_RESEND_IP_LIMITED = 'signup_resend_ip_limited', '가입 코드 재전송: IP 시도 제한'
    PASSWORD_RESET_IP_LIMITED = 'password_reset_ip_limited', '비밀번호 재설정: IP 시도 제한'
    PASSWORD_CHANGE_FAILURES_LIMITED = 'password_change_failures_limited', '비밀번호 변경: 현재 비밀번호 틀림 제한'
    # 공격은 아니지만 운영자가 알아야 하는 사건이라 같은 곳에 남긴다
    MAIL_DISCARDED = 'mail_discarded', '메일: 보내지 못하고 버림'


class SecurityEvent(models.Model):
    """
    운영자가 알아야 할 보안 사건의 기록. "누가 시도 제한에 걸렸는가" 가 남는다.

    시도 횟수는 Redis 에 있고 시간이 지나면 사라진다. 그것만으로는 공격이 있었는지 나중에 알 수 없다.
    남겨야 하는 사실은 여기(PostgreSQL)에 적는다.

    내용은 추가만 한다. 바뀌는 것은 "운영자에게 알렸는가"(reported_at) 뿐이다.
    보관 기간이 지난 기록은 지운다(security_digest.py).
    """

    kind = models.CharField('종류', max_length=40, choices=SecurityEventKind.choices)
    # 시도 횟수를 센 단위다. IPv4 는 주소, IPv6 는 앞 64비트의 묶음(예: 2001:db8:1:2::/64).
    # 로그인한 뒤의 API(비밀번호 변경)에서도 남긴다
    # 요청과 무관한 사건(메일 버림)에서는 비어 있다
    ip = models.CharField('IP', max_length=64, blank=True)
    # 대상이 된 계정. 없는 아이디로 시도했거나 계정과 무관한 제한(IP)이면 비어 있다.
    # 입력된 아이디 문자열은 남기지 않는다. 아이디 칸에 비밀번호를 잘못 넣는 일이 흔하다.
    # 계정이 지워져도 사건의 기록은 남긴다
    user = models.ForeignKey(
        'accounts.User',
        verbose_name='대상 계정',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='security_events',
    )
    created_at = models.DateTimeField('일어난 시각', auto_now_add=True)
    # 요약 메일에 실어 운영자에게 알린 시각. 아직 알리지 않았으면 비어 있다.
    # "지난 한 시간" 처럼 시간으로 자르지 않고 이 표시로 고른다.
    # 요약이 늦게 돌거나 두 번 돌아도 빠지거나 겹치는 사건이 없다
    reported_at = models.DateTimeField('알린 시각', null=True, blank=True)

    class Meta:
        verbose_name = '보안 이벤트'
        verbose_name_plural = '보안 이벤트'
        ordering = ['-created_at']
        indexes = [
            # "지난 한 시간의 사건" 처럼 시간으로 잘라 볼 때 쓴다
            models.Index(fields=['created_at'], name='accounts_secevent_time_idx'),
            # 요약이 "아직 알리지 않은 사건" 을 찾을 때 쓴다. 알린 사건은 색인에 넣지 않는다.
            # 대부분의 행은 알린 사건이라, 색인이 작게 유지된다
            models.Index(
                fields=['created_at'],
                name='accounts_secevent_unrep_idx',
                condition=models.Q(reported_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f'{self.get_kind_display()} / {self.ip or "-"}'


class OutgoingMailStatus(models.TextChoices):
    PENDING = 'pending', '발송 대기'
    DISCARDED = 'discarded', '버림'


class OutgoingMail(models.Model):
    """
    보내야 할 메일. 발송함(outbox)이다.

    요청을 처리하는 쪽은 메일을 직접 보내지 않고 여기에 적기만 한다.
    따로 도는 워커가 꺼내 보낸다. 그래서 메일 서버가 느리거나 죽어도 요청은 영향을 받지 않고,
    응답 시간으로 메일을 보냈는지(= 가입된 주소인지)가 드러나지 않는다.

    보낸 메일의 행은 지운다. 본문에 인증 코드가 들어 있어 남겨 두면 안 된다.
    끝내 못 보낸 메일은 본문만 지우고 행을 남겨, 운영자가 관리자 화면에서 볼 수 있게 한다.
    """

    to_email = models.EmailField('받는 사람')
    subject = models.CharField('제목', max_length=200)
    # 버린 메일은 본문을 비운다
    body = models.TextField('본문', blank=True)

    status = models.CharField(
        '상태',
        max_length=20,
        choices=OutgoingMailStatus.choices,
        default=OutgoingMailStatus.PENDING,
    )
    attempts = models.PositiveSmallIntegerField('시도 횟수', default=0)
    # 마지막 실패의 이유. 메일 서버가 돌려준 오류 문구다
    last_error = models.CharField('마지막 오류', max_length=500, blank=True)

    created_at = models.DateTimeField('만든 시각', auto_now_add=True)
    # 이 시각부터 보낼 수 있다. 실패하면 뒤로 미룬다
    next_attempt_at = models.DateTimeField('다음 시도 시각')
    # 이 시각이 지나면 보내지 않고 버린다. 늦게 도착한 인증 코드는 쓸모가 없다
    expires_at = models.DateTimeField('버리는 시각')
    discarded_at = models.DateTimeField('버린 시각', null=True, blank=True)

    class Meta:
        verbose_name = '보낼 메일'
        verbose_name_plural = '보낼 메일'
        indexes = [
            # 워커가 "지금 보낼 수 있는 대기 중인 메일" 을 찾을 때 쓴다
            models.Index(fields=['status', 'next_attempt_at'], name='accounts_mail_due_idx'),
        ]

    def __str__(self) -> str:
        return f'{self.to_email} / {self.subject}'
