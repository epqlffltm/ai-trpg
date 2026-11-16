# auth-server/accounts/migrations/0042_step_up.py

"""
민감한 작업 앞의 본인 확인(F5)을 위한 변경. 세션마다의 확인 창(StepUpWindow), 본인 확인을 껐는지(User.step_up_disabled),
코드의 용도와 메일 종류에 step_up 을 더한다. 있던 행은 그대로이고 새 칸은 기본값(켜짐)이다.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0041_remove_ai_training_consent"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="step_up_disabled",
            field=models.BooleanField(
                default=False, verbose_name="민감한 작업의 본인 확인 끔"
            ),
        ),
        migrations.AlterField(
            model_name="emailcode",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("signup", "가입 인증"),
                    ("login", "로그인 인증"),
                    ("password_reset", "비밀번호 재설정"),
                    ("step_up", "본인 확인"),
                ],
                max_length=20,
                verbose_name="용도",
            ),
        ),
        migrations.AlterField(
            model_name="outgoingmail",
            name="kind",
            field=models.CharField(
                choices=[
                    ("signup_code", "가입 인증 코드"),
                    ("login_code", "로그인 인증 코드"),
                    ("step_up_code", "본인 확인 코드"),
                    ("already_registered", "이미 가입된 이메일"),
                    ("password_reset", "비밀번호 재설정"),
                    ("password_changed", "비밀번호 변경 알림"),
                    ("security_digest", "보안 이벤트 요약"),
                    ("guardian_consent", "보호자 동의 요청"),
                    ("guardian_consented", "보호자 동의 확인"),
                    ("guardian_revoked", "보호자 동의 철회 확인"),
                    ("minor_guardian", "미성년자에게 보호자 동의 알림"),
                    ("guardian_payment", "보호자에게 결제 알림"),
                    ("payment_receipt", "결제한 본인에게 결제 확인"),
                    ("refund_receipt", "결제한 본인에게 청약철회 확인"),
                    ("withdrawal_requested", "탈퇴 요청 확인"),
                    ("withdrawal_reminder", "탈퇴 하루 전 알림"),
                    ("withdrawal_completed", "탈퇴를 마침"),
                    ("signup_refused", "가입을 받지 않는 이메일"),
                    ("inquiry_reply", "문의의 답"),
                    ("other", "그 밖"),
                ],
                default="other",
                max_length=40,
                verbose_name="종류",
            ),
        ),
        migrations.CreateModel(
            name="StepUpWindow",
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
                ("session_id", models.CharField(max_length=64, verbose_name="세션")),
                (
                    "verified_at",
                    models.DateTimeField(verbose_name="마지막으로 확인한 시각"),
                ),
                ("expires_at", models.DateTimeField(verbose_name="창이 닫히는 시각")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="step_up_windows",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="회원",
                    ),
                ),
            ],
            options={
                "verbose_name": "본인 확인 창",
                "verbose_name_plural": "본인 확인 창",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "session_id"),
                        name="accounts_stepupwindow_user_session_unique",
                    )
                ],
            },
        ),
    ]
