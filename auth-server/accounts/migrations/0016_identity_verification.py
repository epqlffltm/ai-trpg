# auth-server/accounts/migrations/0016_identity_verification.py

"""
휴대폰 본인인증의 기록을 더하고, 환영 크레딧을 본인인증 때로 옮긴다(#336).

- 본인인증의 표. 계정마다 하나, 사람(DI 의 서명)마다 하나다
- 환영 크레딧의 '메일함의 열쇠'를 '받는 사람의 열쇠'로 이름만 바꾼다. 이미 적힌 줄의 값은 그대로다
  (그 줄의 계정과 메일함은 다시 받지 않는다)
- 보안 이벤트에 본인인증의 종류 둘을 더한다
"""

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_session_revocations"),
    ]

    operations = [
        migrations.RenameField(
            model_name="welcomecredit",
            old_name="mailbox_key",
            new_name="recipient_key",
        ),
        migrations.AlterField(
            model_name="welcomecredit",
            name="recipient_key",
            field=models.CharField(max_length=64, unique=True, verbose_name="받는 사람의 열쇠"),
        ),
        migrations.AlterField(
            model_name="securityevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("login_ip_limited", "로그인: IP 시도 제한"),
                    ("login_failures_limited", "로그인: 비밀번호 틀림 제한"),
                    (
                        "reserved_username_login",
                        "로그인: 예약어 아이디로 시도해 IP 차단",
                    ),
                    ("signup_ip_limited", "가입: IP 시도 제한"),
                    ("signup_resend_ip_limited", "가입 코드 재전송: IP 시도 제한"),
                    ("password_reset_ip_limited", "비밀번호 재설정: IP 시도 제한"),
                    (
                        "password_change_failures_limited",
                        "비밀번호 변경: 현재 비밀번호 틀림 제한",
                    ),
                    ("mail_discarded", "메일: 보내지 못하고 버림"),
                    ("account_suspended", "계정: 정지"),
                    ("account_restored", "계정: 정지를 풂"),
                    ("identity_under_age", "본인인증: 만 14세 미만이라 계정을 막음"),
                    ("identity_in_use", "본인인증: 다른 계정에서 인증한 사람"),
                ],
                max_length=40,
                verbose_name="종류",
            ),
        ),
        migrations.CreateModel(
            name="IdentityVerification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("person_key", models.CharField(max_length=64, unique=True, verbose_name="사람 열쇠")),
                (
                    "legal_adult_from",
                    models.DateField(blank=True, null=True, verbose_name="성년이 되는 날"),
                ),
                (
                    "adult_content_from",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="성인용 내용을 볼 수 있게 되는 날",
                    ),
                ),
                ("provider", models.CharField(max_length=20, verbose_name="업체")),
                ("verified_at", models.DateTimeField(verbose_name="인증한 시각")),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="identity_verification",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="회원",
                    ),
                ),
            ],
            options={
                "verbose_name": "본인인증",
                "verbose_name_plural": "본인인증",
            },
        ),
    ]
