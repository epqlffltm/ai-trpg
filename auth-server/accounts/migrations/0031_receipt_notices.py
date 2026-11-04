# auth-server/accounts/migrations/0031_receipt_notices.py

"""
결제한 본인에게 보내는 결제·청약철회 메일의 기록(#553)과 그 메일의 종류(payment_receipt, refund_receipt).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0030_invites"),
    ]

    operations = [
        migrations.AlterField(
            model_name="outgoingmail",
            name="kind",
            field=models.CharField(
                choices=[
                    ("signup_code", "가입 인증 코드"),
                    ("login_code", "로그인 인증 코드"),
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
                    ("other", "그 밖"),
                ],
                default="other",
                max_length=40,
                verbose_name="종류",
            ),
        ),
        migrations.CreateModel(
            name="ReceiptNotice",
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
                ("order_id", models.UUIDField(verbose_name="주문 번호")),
                (
                    "kind",
                    models.CharField(
                        choices=[("paid", "결제"), ("refunded", "청약철회")],
                        max_length=20,
                        verbose_name="종류",
                    ),
                ),
                (
                    "user_public_id",
                    models.UUIDField(verbose_name="결제한 사람의 공개 ID"),
                ),
                ("product_id", models.CharField(max_length=100, verbose_name="상품")),
                ("price", models.PositiveBigIntegerField(verbose_name="값")),
                ("credits", models.PositiveBigIntegerField(verbose_name="크레딧")),
                ("paid_at", models.DateTimeField(verbose_name="결제가 끝난 시각")),
                (
                    "occurred_at",
                    models.DateTimeField(verbose_name="결제나 청약철회가 끝난 시각"),
                ),
                (
                    "refundable_until",
                    models.DateTimeField(verbose_name="청약철회 기한"),
                ),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("queued", "메일을 적음"),
                            ("skipped", "알릴 계정이 없음"),
                        ],
                        max_length=20,
                        verbose_name="결과",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="받은 시각"),
                ),
                (
                    "receipt",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="receipt_notice",
                        to="accounts.mailreceipt",
                        verbose_name="보낸 메일의 기록",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="receipt_notices",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="결제한 사람",
                    ),
                ),
            ],
            options={
                "verbose_name": "본인 결제 알림",
                "verbose_name_plural": "본인 결제 알림",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("order_id", "kind"), name="accounts_receiptnotice_once"
                    )
                ],
            },
        ),
    ]
