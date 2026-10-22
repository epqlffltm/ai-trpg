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

    # 세션 버전을 마지막으로 올린 시각. 비어 있으면 한 번도 끊은 적이 없다.
    # 다른 서버는 세션 버전을 모른다. 이 시각이 access 토큰의 수명 안이면
    # 끊긴 세션 목록에 싣는다(session_revocations.py)
    sessions_revoked_at = models.DateTimeField('세션을 끊은 시각', null=True, blank=True, db_index=True)

    # 탈퇴를 요청한 시각(#603, docs/architecture/withdrawal.md). 비어 있으면 요청하지 않았거나 취소했다.
    # 이 시각에서 유예(withdrawal.GRACE)가 지나면 정리 작업이 계정을 비운다. 그동안의 토큰은 인증 서버에만 통한다
    withdrawal_requested_at = models.DateTimeField('탈퇴를 요청한 시각', null=True, blank=True, db_index=True)
    # 탈퇴를 마친 시각. 계정을 비운 때다. 마친 계정은 되돌리지 않는다
    withdrawn_at = models.DateTimeField('탈퇴를 마친 시각', null=True, blank=True)
    # 마치기 하루 전의 알림 메일을 보낸 시각(#624). 요청마다 한 통만 보내려고 적는다.
    # 요청할 때 비운다. 취소하고 다시 요청하면 새 요청에 한 통을 더 보낸다
    withdrawal_reminded_at = models.DateTimeField('탈퇴 하루 전 알림을 보낸 시각', null=True, blank=True)

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

    # 옛 가입 흐름(미인증 계정에 코드를 붙이던 것)의 값이다. 새로 발급하지 않는다.
    # 가입 코드는 계정이 생기기 전이라 이메일에 붙는다(SignupCode). 값은 지난 행 때문에 남긴다
    SIGNUP = 'signup', '가입 인증'
    LOGIN = 'login', '로그인 인증'
    PASSWORD_RESET = 'password_reset', '비밀번호 재설정'


class CodeRecord(models.Model):
    """
    메일로 보낸 코드 하나와 그 발급 이력. 표가 아니라 두 표(EmailCode, SignupCode)가 함께 쓰는 칸이다.

    자리마다 행이 하나뿐이다. 새 코드를 발급하면 행을 새로 만들지 않고 덮어쓴다.
    그래서 테이블이 계속 불어나지 않고, 만료된 코드를 따로 지울 필요가 없다.
    발급과 검증의 규칙은 email_codes.py 한 곳에 있다.
    """

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
        abstract = True


class EmailCode(CodeRecord):
    """회원에게 용도마다 보낸 인증 코드(로그인, 비밀번호 재설정)."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='email_codes',
        verbose_name='회원',
    )
    purpose = models.CharField('용도', max_length=20, choices=EmailCodePurpose.choices)

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


class SignupCode(CodeRecord):
    """
    가입하려는 이메일로 보낸 코드(#271).

    가입은 이메일의 주인임을 먼저 확인하고, 그 뒤에 계정을 만든다. 그래서 코드가 계정이 아니라 이메일에 붙는다.
    이미 가입된 주소로 보내는 안내 메일도 같은 행으로 센다. 두 경우가 같은 발급 제한을 써야
    응답이나 메일의 수로 가입 여부가 드러나지 않는다.

    가입을 마쳐도 행을 지우지 않는다. 발급 이력이 남아야 제한을 지킨다. 오래된 행은 정리 명령이 지운다.
    """

    # 소문자로 적는다(services.py). 같은 주소의 대소문자 차이로 행이 둘 생기지 않는다
    email = models.EmailField('이메일', unique=True)

    class Meta:
        verbose_name = '가입 코드'
        verbose_name_plural = '가입 코드'

    def __str__(self) -> str:
        return self.email


class SecurityEventKind(models.TextChoices):
    LOGIN_IP_LIMITED = 'login_ip_limited', '로그인: IP 시도 제한'
    LOGIN_FAILURES_LIMITED = 'login_failures_limited', '로그인: 비밀번호 틀림 제한'
    RESERVED_USERNAME_LOGIN = 'reserved_username_login', '로그인: 예약어 아이디로 시도해 IP 차단'
    SIGNUP_IP_LIMITED = 'signup_ip_limited', '가입: IP 시도 제한'
    # 옛 signup/resend 의 것이다. 다시 보내기가 signup 으로 합쳐져(#271) 새로 생기지 않는다. 지난 기록 때문에 남긴다
    SIGNUP_RESEND_IP_LIMITED = 'signup_resend_ip_limited', '가입 코드 재전송: IP 시도 제한'
    PASSWORD_RESET_IP_LIMITED = 'password_reset_ip_limited', '비밀번호 재설정: IP 시도 제한'
    PASSWORD_CHANGE_FAILURES_LIMITED = 'password_change_failures_limited', '비밀번호 변경: 현재 비밀번호 틀림 제한'
    # 공격은 아니지만 운영자가 알아야 하는 사건이라 같은 곳에 남긴다
    MAIL_DISCARDED = 'mail_discarded', '메일: 보내지 못하고 버림'
    # 운영자가 한 일이다. 사유(note)를 함께 남긴다
    ACCOUNT_SUSPENDED = 'account_suspended', '계정: 정지'
    ACCOUNT_RESTORED = 'account_restored', '계정: 정지를 풂'
    # 본인인증(#336). 만 14세 미만이라 계정을 막고 개인정보를 지웠다
    IDENTITY_UNDER_AGE = 'identity_under_age', '본인인증: 만 14세 미만이라 계정을 막음'
    # 다른 계정이 이미 인증한 사람이다. 부모의 휴대폰이나 계정을 여럿 만드는 것을 운영자가 알아본다
    IDENTITY_IN_USE = 'identity_in_use', '본인인증: 다른 계정에서 인증한 사람'
    # 탈퇴(#603). 요청은 계정을 빼앗긴 신호일 수 있어 운영자가 본다. 마친 것은 계정을 비웠다는 기록이다
    WITHDRAWAL_REQUESTED = 'withdrawal_requested', '탈퇴: 요청'
    ACCOUNT_WITHDRAWN = 'account_withdrawn', '탈퇴: 계정을 비움'


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
    # 운영자가 남긴 사유. 계정을 정지하거나 풀 때만 적는다. 다른 사건에서는 비어 있다.
    # 비밀번호, 코드, 이메일 주소 같은 것은 적지 않는다(명령이 길이만 막고 내용은 보지 못한다)
    note = models.CharField('사유', max_length=200, blank=True)
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


class SuspensionReason(models.TextChoices):
    """
    정지의 사유(#634). 운영자가 정지할 때 하나를 고른다(suspend_account --kind).

    정지된 채 탈퇴한 사람이 다시 가입할 때 무엇을 막고 얼마 동안 막을지가 사유마다 다르다(#634 의 사유 표).
    """

    SPAM = 'spam', '도배, 광고'
    ABUSE = 'abuse', '욕설, 괴롭힘, 혐오'
    FRAUD = 'fraud', '결제 사기, 청약철회 악용, 계정 거래'
    ILLEGAL = 'illegal', '해킹, 서비스 공격 같은 불법 행위'
    OTHER = 'other', '그 밖(운영자 판단)'


class Suspension(models.Model):
    """
    계정 정지의 기록(#634). 정지할 때 한 줄을 적고, 풀 때 그 줄에 푼 시각을 적는다(suspension.py).

    보안 이벤트에도 남지만 그것은 30일 뒤에 지워진다. 정지는 그보다 오래가고, 탈퇴를 마칠 때
    정지 중인지와 그 사유를 알아야 한다. 그래서 따로 둔다. 풀리지 않은 정지는 계정마다 하나다.
    """

    user = models.ForeignKey('accounts.User', verbose_name='계정', on_delete=models.CASCADE, related_name='suspensions')
    reason = models.CharField('사유의 종류', max_length=20, choices=SuspensionReason.choices)
    # 운영자가 남긴 사유. 보안 이벤트의 사유(SecurityEvent.note)와 같은 글이다
    note = models.CharField('사유', max_length=200)
    suspended_at = models.DateTimeField('정지한 시각')
    # 비어 있으면 아직 정지 중이다
    restored_at = models.DateTimeField('푼 시각', null=True, blank=True)
    restore_note = models.CharField('푼 사유', max_length=200, blank=True)

    class Meta:
        verbose_name = '정지'
        verbose_name_plural = '정지'
        ordering = ['-suspended_at']
        constraints = [
            # 풀리지 않은 정지는 계정마다 하나다. 정지와 풀기는 계정의 줄을 잠그고 한다(suspension.py)
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(restored_at__isnull=True),
                name='accounts_one_open_suspension',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.user} / {self.get_reason_display()} / {"풀림" if self.restored_at else "정지 중"}'


class OutgoingMailStatus(models.TextChoices):
    PENDING = 'pending', '발송 대기'
    # 워커가 차지하고 메일 서버와 통신하는 중이다. 다음 시도 시각이 임대가 끝나는 시각이다
    SENDING = 'sending', '보내는 중'
    DISCARDED = 'discarded', '버림'


class MailKind(models.TextChoices):
    """
    메일의 종류. 메트릭 emails_sent_total 의 kind 다(docs/observability.md).
    문구를 만드는 쪽(accounts/mail.py)이 정한다.

    종류를 더하면 이 목록과 문서의 표에 함께 더한다. 메트릭의 label 이라 값의 종류가 정해져 있어야 한다.
    """

    SIGNUP_CODE = 'signup_code', '가입 인증 코드'
    LOGIN_CODE = 'login_code', '로그인 인증 코드'
    ALREADY_REGISTERED = 'already_registered', '이미 가입된 이메일'
    PASSWORD_RESET = 'password_reset', '비밀번호 재설정'
    PASSWORD_CHANGED = 'password_changed', '비밀번호 변경 알림'
    SECURITY_DIGEST = 'security_digest', '보안 이벤트 요약'
    GUARDIAN_CONSENT = 'guardian_consent', '보호자 동의 요청'
    GUARDIAN_CONSENTED = 'guardian_consented', '보호자 동의 확인'
    GUARDIAN_REVOKED = 'guardian_revoked', '보호자 동의 철회 확인'
    MINOR_GUARDIAN = 'minor_guardian', '미성년자에게 보호자 동의 알림'
    GUARDIAN_PAYMENT = 'guardian_payment', '보호자에게 결제 알림'
    WITHDRAWAL_REQUESTED = 'withdrawal_requested', '탈퇴 요청 확인'
    WITHDRAWAL_REMINDER = 'withdrawal_reminder', '탈퇴 하루 전 알림'
    WITHDRAWAL_COMPLETED = 'withdrawal_completed', '탈퇴를 마침'
    # 종류를 적지 않은 메일. 이 칸이 생기기 전에 적힌 것도 이것이다
    OTHER = 'other', '그 밖'


class MailReceipt(models.Model):
    """
    보낸 메일의 기록(#352). 발송함의 줄은 보내면 지우므로(본문에 인증 코드가 있어서) 보냈다는 사실이 남지 않는다.
    보냈다는 것을 남겨야 하는 메일(보호자의 결제 알림)만 이 기록을 붙여 적는다.

    받는 사람, 제목, 본문은 적지 않는다. 메일 서버가 받았는지와 그 시각만 남긴다.
    "그 주소로 그날 보냈고 메일 서버가 받았다"를 보여 주는 데 쓴다. 받는 사람이 읽었는지는 알 수 없다.
    """

    # 무엇의 기록인지. guardian_payment_notice 같은 글자다
    purpose = models.CharField('용도', max_length=40)
    created_at = models.DateTimeField('적은 시각', auto_now_add=True)
    # 메일 서버가 받은 시각. 비어 있으면 아직 보내지 못했다
    sent_at = models.DateTimeField('보낸 시각', null=True, blank=True)
    # 끝내 보내지 못하고 버린 시각
    discarded_at = models.DateTimeField('버린 시각', null=True, blank=True)

    class Meta:
        verbose_name = '보낸 메일의 기록'
        verbose_name_plural = '보낸 메일의 기록'

    def __str__(self) -> str:
        return f'{self.purpose} / {self.sent_at or self.discarded_at or "보내기 전"}'


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
    # 메일의 종류. 보낸 결과를 종류마다 센다(메트릭 emails_sent_total)
    kind = models.CharField('종류', max_length=40, choices=MailKind.choices, default=MailKind.OTHER)
    # 암호화된 본문이다(mail_crypto.py). 버린 메일은 본문을 비운다
    body = models.TextField('본문', blank=True)

    status = models.CharField(
        '상태',
        max_length=20,
        choices=OutgoingMailStatus.choices,
        default=OutgoingMailStatus.PENDING,
    )
    # 워커가 차지한 횟수다. 차지할 때마다 하나 오른다
    attempts = models.PositiveSmallIntegerField('시도 횟수', default=0)
    # 마지막 실패의 이유. 메일 서버가 돌려준 오류 문구다
    last_error = models.CharField('마지막 오류', max_length=500, blank=True)

    created_at = models.DateTimeField('만든 시각', auto_now_add=True)
    # 이 시각부터 보낼 수 있다. 실패하면 뒤로 미룬다. 보내는 중이면 임대가 끝나는 시각이다
    next_attempt_at = models.DateTimeField('다음 시도 시각')
    # 이 시각이 지나면 보내지 않고 버린다. 늦게 도착한 인증 코드는 쓸모가 없다
    expires_at = models.DateTimeField('버리는 시각')
    discarded_at = models.DateTimeField('버린 시각', null=True, blank=True)
    # 보냈다는 것을 남길 메일이면 그 기록. 메일의 줄은 보내면 지워지고 기록은 남는다
    receipt = models.ForeignKey(
        MailReceipt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mails',
        verbose_name='보낸 메일의 기록',
    )

    class Meta:
        verbose_name = '보낼 메일'
        verbose_name_plural = '보낼 메일'
        indexes = [
            # 워커가 "지금 보낼 수 있는 메일"(대기 중이거나 임대가 끝난 것)을 찾을 때 쓴다
            models.Index(fields=['status', 'next_attempt_at'], name='accounts_mail_due_idx'),
        ]

    def __str__(self) -> str:
        return f'{self.to_email} / {self.subject}'


class WelcomeCreditStatus(models.TextChoices):
    PENDING = 'pending', '맡기기 전'
    GRANTED = 'granted', '지급됨'
    ALREADY_GRANTED = 'already_granted', '이미 받은 사용자'
    DISABLED = 'disabled', '결제 서버가 꺼 둠'


class WelcomeCredit(models.Model):
    """
    환영 크레딧을 받을 사람 하나. 두 가지 일을 한다.

    하나는 "이 사람은 이미 받았다"는 기록이다. 사람마다 한 줄만 있을 수 있다.
    계정을 지우고 다시 가입해 본인인증을 해도 줄은 하나다.

    다른 하나는 결제 서버에 맡길 일의 목록(outbox)이다. 본인인증과 같은 트랜잭션에서 적고,
    따로 도는 워커(manage.py send_welcome_credits)가 꺼내 결제 서버에 맡긴다.
    그래서 결제 서버가 느리거나 죽어도 본인인증은 영향을 받지 않고, 살아나면 지급된다.

    끝난 줄도 지우지 않는다. 지우면 "이미 받았다"는 기록이 사라진다.
    """

    # 받는 사람의 열쇠. 본인인증의 사람 열쇠(IdentityVerification.person_key)와 같은 값이다(identity.py).
    # #336 전에 적힌 줄은 메일함(이메일 주소를 정리한 것)의 열쇠다. 섞는 비밀이 달라 두 열쇠가 겹치지 않는다.
    # 계정을 지운 뒤에도 이 줄은 남는다. 그래서 DI 나 주소를 그대로 적지 않고 서버의 비밀키로 서명한 값만 적는다
    recipient_key = models.CharField('받는 사람의 열쇠', max_length=64, unique=True)
    # 받을 사용자의 공개 ID. 결제 서버가 아는 사용자 번호다. 한 계정은 한 번만 받는다(welcome_credit.py).
    # 외래 키로 두지 않는다. 계정이 지워져도 이 줄은 남아야 한다
    user_public_id = models.UUIDField('받는 사용자의 공개 ID')

    status = models.CharField(
        '상태',
        max_length=20,
        choices=WelcomeCreditStatus.choices,
        default=WelcomeCreditStatus.PENDING,
    )
    attempts = models.PositiveIntegerField('시도 횟수', default=0)
    # 마지막 실패의 이유. 상태 코드나 오류의 종류다
    last_error = models.CharField('마지막 오류', max_length=200, blank=True)

    created_at = models.DateTimeField('만든 시각', auto_now_add=True)
    # 이 시각부터 맡길 수 있다. 실패하면 뒤로 미룬다
    next_attempt_at = models.DateTimeField('다음 시도 시각')
    finished_at = models.DateTimeField('끝난 시각', null=True, blank=True)

    class Meta:
        verbose_name = '환영 크레딧'
        verbose_name_plural = '환영 크레딧'
        indexes = [
            # 워커가 "지금 맡길 수 있는 줄" 을 찾을 때 쓴다
            models.Index(fields=['status', 'next_attempt_at'], name='accounts_welcome_due_idx'),
        ]

    def __str__(self) -> str:
        return f'{self.user_public_id} / {self.get_status_display()}'


class IdentityVerification(models.Model):
    """
    휴대폰 본인인증을 마친 기록(#336). 계정마다 하나, 사람마다 하나다.

    한 사람은 한 계정에서만 인증한다. 계정을 지우면 이 기록도 지워져, 같은 사람이 새 계정에서 다시 인증할 수 있다.
    환영 크레딧은 사람에게 한 번이라 그때는 다시 받지 못한다(WelcomeCredit 은 지우지 않는다).

    업체가 준 것 가운데 남기는 것은 사람 열쇠와 두 날짜뿐이다. DI, 생일, 이름, 전화번호는 적지 않는다.
    날짜는 아직 오지 않았을 때만 적는다. 이미 지났으면 비운다. 성인의 날짜를 적어 두면 그것이 곧 생일이다.
    미성년자의 날짜는 그날 저절로 성인이 되게 하려고 적는다. 다시 인증하지 않아도 된다(age.has_reached).
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='identity_verification',
        verbose_name='회원',
    )
    # 업체가 준 DI 를 서버의 비밀키로 서명한 값이다(identity.py). DI 는 짐작할 수 없지만,
    # 다른 서비스와 함께 쓰는 값(CI)처럼 바깥에서 이어 붙이지 못하게 그대로 적지 않는다
    person_key = models.CharField('사람 열쇠', max_length=64, unique=True)
    # 민법의 성년이 되는 날(만 19세 생일). 결제가 본다. 비어 있으면 인증할 때 이미 성년이었다
    legal_adult_from = models.DateField('성년이 되는 날', null=True, blank=True)
    # 청소년 보호법의 청소년이 아니게 되는 날(만 19세가 되는 해의 1월 1일). 성인용 내용이 본다.
    # 비어 있으면 인증할 때 이미 지났다
    adult_content_from = models.DateField('성인용 내용을 볼 수 있게 되는 날', null=True, blank=True)
    # 확인해 준 업체(config/identity.py). 가짜 업체로 한 인증을 나중에 가려낼 수 있다
    provider = models.CharField('업체', max_length=20)
    verified_at = models.DateTimeField('인증한 시각')

    class Meta:
        verbose_name = '본인인증'
        verbose_name_plural = '본인인증'

    def __str__(self) -> str:
        return f'{self.user} / {self.provider}'


class GuardianConsentStatus(models.TextChoices):
    REQUESTED = 'requested', '동의를 기다림'
    CONSENTED = 'consented', '동의함'
    REVOKED = 'revoked', '철회함'


class GuardianConsent(models.Model):
    """
    미성년자(만 19세 미만)의 결제에 대한 보호자의 동의(#336). 미성년자마다 하나다. 보호자는 한 명이다.

    보호자는 계정을 만들지 않는다. 미성년자가 보호자의 이메일을 적으면 그 주소로 동의 링크가 가고,
    보호자가 링크에서 휴대폰 본인인증을 하고 동의한다. 철회는 동의를 알리는 메일과 결제 알림 메일의 링크로 한다.

    동의는 미성년자가 성년이 되는 날(IdentityVerification.legal_adult_from)이나 보호자가 철회할 때까지다.
    성년이 되는 날을 따로 적지 않는다. 결제 서버가 그 날짜를 함께 받아 스스로 센다(payment_eligibility.py).
    동의한 동안에는 미성년자가 보호자를 바꿀 수 없다.
    바꾸게 하면 아무 성인에게 다시 동의를 받아 보호자의 철회를 피할 수 있다.
    """

    minor = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='guardian_consent',
        verbose_name='미성년자',
    )
    # 동의 링크와 결제 알림을 보낼 곳. 철회하면 비운다. 더 보낼 일이 없다
    guardian_email = models.EmailField('보호자의 이메일', blank=True)
    status = models.CharField('상태', max_length=20, choices=GuardianConsentStatus.choices)
    # 링크에 서명해 넣는 값(guardian_links.py). 새로 요청하면 바뀌어 앞서 보낸 링크를 쓸 수 없게 된다
    link_nonce = models.CharField('링크의 일회 값', max_length=32)
    # 동의한 보호자의 사람 열쇠(identity.person_key). 미성년자 본인이 아닌지 보는 데 쓰고,
    # 다툼이 생기면 누가 동의했는지 맞춰 본다
    guardian_person_key = models.CharField('보호자의 사람 열쇠', max_length=64, blank=True)

    requested_at = models.DateTimeField('요청한 시각')
    consented_at = models.DateTimeField('동의한 시각', null=True, blank=True)
    revoked_at = models.DateTimeField('철회한 시각', null=True, blank=True)

    # 요청 메일의 발송 제한. 남의 메일함에 링크를 퍼붓지 못하게 한다(guardian.py)
    window_started_at = models.DateTimeField('요청 횟수를 세기 시작한 시각')
    requests_in_window = models.PositiveSmallIntegerField('구간 안의 요청 횟수', default=0)

    class Meta:
        verbose_name = '보호자 동의'
        verbose_name_plural = '보호자 동의'

    def __str__(self) -> str:
        return f'{self.minor} / {self.get_status_display()}'


class PaymentEligibility(models.Model):
    """
    결제 서버에 알릴 결제 자격(#336, 결제 서버의 #337). 본인인증을 마친 계정마다 하나다.

    알리는 것은 사건이 아니라 지금의 상태다(성년이 되는 날, 보호자 동의). 바뀔 때마다 버전을 올리고,
    워커가 그때의 상태를 버전과 함께 보낸다. 결제 서버는 가진 것보다 높은 버전만 받는다.
    그래서 늦게 도착하거나 두 번 도착해도, 사이의 변경을 몇 번 건너뛰어도 마지막 상태로 맞는다.
    결제 서버는 결제할 때 이 서버를 부르지 않는다. 자기 DB 에 받아 둔 것만 본다.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='payment_eligibility',
        verbose_name='회원',
    )
    # 상태가 바뀔 때마다 하나 오른다
    version = models.PositiveBigIntegerField('버전', default=0)
    # 결제 서버가 받았다고 답한 가장 높은 버전. version 보다 작으면 보낼 일이 있다
    delivered_version = models.PositiveBigIntegerField('알린 버전', default=0)

    attempts = models.PositiveIntegerField('시도 횟수', default=0)
    last_error = models.CharField('마지막 오류', max_length=200, blank=True)
    # 이 시각부터 보낼 수 있다. 실패하면 뒤로 미룬다. 워커가 보내는 동안은 임대가 끝나는 시각이다
    next_attempt_at = models.DateTimeField('다음 시도 시각')

    class Meta:
        verbose_name = '결제 자격 알림'
        verbose_name_plural = '결제 자격 알림'
        indexes = [
            # 워커가 "보낼 것이 있고 때가 된 줄" 을 찾을 때 쓴다. 다 알린 줄은 색인에 넣지 않는다
            models.Index(
                fields=['next_attempt_at'],
                name='accounts_eligibility_due_idx',
                condition=models.Q(version__gt=models.F('delivered_version')),
            ),
        ]

    def __str__(self) -> str:
        return f'{self.user} / {self.delivered_version}/{self.version}'


class GuardianNoticeKind(models.TextChoices):
    PAID = 'paid', '결제'
    REFUNDED = 'refunded', '청약철회'


class GuardianNoticeOutcome(models.TextChoices):
    # 보호자에게 보낼 메일을 적었다
    QUEUED = 'queued', '메일을 적음'
    # 알릴 보호자가 없다(그새 동의를 철회했다, 계정이 지워졌다)
    SKIPPED = 'skipped', '알릴 보호자가 없음'


class GuardianNotice(models.Model):
    """
    결제 서버가 보낸 보호자 알림 하나(#352). 미성년자의 결제와 청약철회다.

    주문과 종류(결제, 청약철회)마다 한 줄이다. 결제 서버가 답을 못 받고 다시 보내도 메일은 한 번만 간다.
    메일을 보냈는지는 붙인 기록(MailReceipt)이 남긴다.
    """

    # 결제 서버의 주문 번호
    order_id = models.UUIDField('주문 번호')
    kind = models.CharField('종류', max_length=20, choices=GuardianNoticeKind.choices)
    # 결제한 미성년자. 계정이 지워져도 기록은 남긴다
    minor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='guardian_notices',
        verbose_name='미성년자',
    )
    minor_public_id = models.UUIDField('미성년자의 공개 ID')
    product_id = models.CharField('상품', max_length=100)
    # 원(KRW)이다
    price = models.PositiveBigIntegerField('값')
    credits = models.PositiveBigIntegerField('크레딧')
    occurred_at = models.DateTimeField('결제나 청약철회가 끝난 시각')
    outcome = models.CharField('결과', max_length=20, choices=GuardianNoticeOutcome.choices)
    receipt = models.OneToOneField(
        MailReceipt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='guardian_notice',
        verbose_name='보낸 메일의 기록',
    )
    created_at = models.DateTimeField('받은 시각', auto_now_add=True)

    class Meta:
        verbose_name = '보호자 결제 알림'
        verbose_name_plural = '보호자 결제 알림'
        constraints = [
            models.UniqueConstraint(fields=['order_id', 'kind'], name='accounts_guardiannotice_once'),
        ]

    def __str__(self) -> str:
        return f'{self.order_id} / {self.get_kind_display()} / {self.get_outcome_display()}'


class ConsentItem(models.TextChoices):
    """
    동의를 받는 항목(#450). 판과 필수 여부는 코드의 표(consents.py 의 POLICIES)에 있다.

    개인정보 처리방침은 동의를 받는 문서가 아니라 알리는 문서라 항목이 아니다. 수집·이용의 동의(privacy)를 따로 받는다.
    """

    TERMS = 'terms', '이용약관'
    PRIVACY = 'privacy', '개인정보 수집·이용'
    MARKETING = 'marketing', '마케팅 정보 수신'
    AI_TRAINING = 'ai_training', '대화 기록의 AI 학습 이용'


class ConsentAction(models.TextChoices):
    AGREED = 'agreed', '동의함'
    WITHDRAWN = 'withdrawn', '철회함'


class ConsentRecord(models.Model):
    """
    동의와 철회 하나(#450). 덮어쓰지 않고 쌓는다. 항목마다 마지막 줄이 지금의 상태다.

    언제 어느 판에 동의했고 언제 철회했는지를 보일 수 있게 한다. 줄을 고치는 코드는 없다(consents.py 는 넣기만 한다).
    IP 와 기기는 적지 않는다. 동의를 보이는 데는 계정, 항목, 판, 시각으로 충분하고, 모으는 개인정보를 늘리지 않는다.
    계정의 줄을 지우면 함께 지워진다. 만 14세 미만으로 막은 계정의 것은 막을 때 지운다(identity.py).
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='consent_records',
        verbose_name='계정',
    )
    item = models.CharField('항목', max_length=32, choices=ConsentItem.choices)
    # 동의했으면 동의한 판, 철회했으면 철회한 그 동의의 판이다
    version = models.PositiveIntegerField('판')
    action = models.CharField('무엇을', max_length=16, choices=ConsentAction.choices)
    at = models.DateTimeField('시각')

    class Meta:
        verbose_name = '동의 기록'
        verbose_name_plural = '동의 기록'
        indexes = [
            # 한 사람의 동의를 읽는다. 사람마다 몇 줄뿐이다
            models.Index(fields=['user', 'item', 'at'], name='accounts_consent_user_item'),
        ]

    def __str__(self) -> str:
        return f'{self.user} / {self.get_item_display()} {self.version}판 / {self.get_action_display()}'


class WithdrawalTarget(models.TextChoices):
    """
    탈퇴를 알릴 서버(#603). 탈퇴를 마칠 때 모든 서버에 줄을 적는다. 비밀을 적은 서버에만 보낸다(withdrawal_client.py).
    새 서버(chat, story)는 받는 주소를 만들 때 여기와 withdrawal_client.DESTINATIONS 에 더한다.
    """

    BILLING = 'billing', '결제 서버'
    NOTIFICATION = 'notification', '알림 서버'
    GAME = 'game', '게임 서버'
    BOARD = 'board', '게시판 서버'
    ASSET = 'asset', 'asset 서버'


class WithdrawalNotice(models.Model):
    """
    탈퇴를 다른 서버에 알릴 일 하나(#603). 탈퇴를 마치는 트랜잭션에서 서버마다 한 줄을 적는다.

    워커가 서명해 보내고, 그 서버가 2xx 로 답할 때까지 다시 보낸다. 버리지 않는다. 늦게 알려도 정리는 해야 한다.
    받는 서버는 같은 알림을 두 번 받아도 결과가 같다. 그래서 워커가 보낸 뒤 죽어 다시 보내도 된다.
    계정의 줄은 탈퇴한 뒤에도 남으므로(비운다) 이 줄도 계정을 가리킨다. 보내는 것은 계정의 공개 ID 다.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_notices', verbose_name='계정')
    target = models.CharField('알릴 서버', max_length=32, choices=WithdrawalTarget.choices)
    # 탈퇴를 마친 시각. 받는 서버에 그대로 보낸다
    withdrawn_at = models.DateTimeField('탈퇴를 마친 시각')
    # 받는 서버가 2xx 로 답한 시각. 비어 있으면 아직 보낼 일이 있다
    delivered_at = models.DateTimeField('알린 시각', null=True, blank=True)

    attempts = models.PositiveIntegerField('시도 횟수', default=0)
    last_error = models.CharField('마지막 오류', max_length=200, blank=True)
    # 이 시각부터 보낼 수 있다. 실패하면 뒤로 미룬다. 워커가 보내는 동안은 임대가 끝나는 시각이다
    next_attempt_at = models.DateTimeField('다음 시도 시각')

    class Meta:
        verbose_name = '탈퇴 알림'
        verbose_name_plural = '탈퇴 알림'
        constraints = [
            # 한 계정의 탈퇴는 서버마다 한 번 알린다
            models.UniqueConstraint(fields=['user', 'target'], name='accounts_withdrawal_notice_once'),
        ]
        indexes = [
            # 워커가 "알릴 것이 있고 때가 된 줄" 을 찾을 때 쓴다. 다 알린 줄은 색인에 넣지 않는다
            models.Index(
                fields=['next_attempt_at'],
                name='accounts_withdrawal_due_idx',
                condition=models.Q(delivered_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f'{self.user} / {self.get_target_display()} / {"알림" if self.delivered_at else "보낼 것"}'
