# auth-server/support/migrations/0001_initial.py

"""
문의의 표(support/models.py). 관리 서버가 생기면 그리로 옮긴다.
"""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0039_inquiry_kinds"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Inquiry",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("account", "계정·로그인"),
                            ("payment", "결제·환불"),
                            ("report", "신고"),
                            ("bug", "오류"),
                            ("other", "그 밖"),
                        ],
                        max_length=20,
                        verbose_name="종류",
                    ),
                ),
                ("title", models.CharField(max_length=100, verbose_name="제목")),
                ("body", models.TextField(verbose_name="내용")),
                (
                    "email",
                    models.EmailField(max_length=254, verbose_name="답 받을 주소"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "답을 기다림"), ("answered", "답함")],
                        default="open",
                        max_length=20,
                        verbose_name="상태",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="보낸 시각"),
                ),
                ("reply", models.TextField(blank=True, verbose_name="답")),
                (
                    "answered_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="답한 시각"
                    ),
                ),
                (
                    "answered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="답한 운영자",
                    ),
                ),
                (
                    "reply_receipt",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="accounts.mailreceipt",
                        verbose_name="답 메일의 기록",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inquiries",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="보낸 계정",
                    ),
                ),
            ],
            options={
                "verbose_name": "문의",
                "verbose_name_plural": "문의",
                "indexes": [
                    models.Index(
                        fields=["status", "-created_at"], name="inquiry_status_recent"
                    ),
                    models.Index(
                        fields=["user", "-created_at"], name="inquiry_user_recent"
                    ),
                ],
            },
        ),
    ]
