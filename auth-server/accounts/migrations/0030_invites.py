# auth-server/accounts/migrations/0030_invites.py

"""
초대 코드와 초대, 초대 보상, 결제 서버에 맡길 초대 보상의 지급(#990).
"""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0029_withdrawal_story"),
    ]

    operations = [
        migrations.CreateModel(
            name="Invitation",
            fields=[
                (
                    "invitee",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="invitation",
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="초대받은 계정",
                    ),
                ),
                (
                    "inviter_public_id",
                    models.UUIDField(
                        db_index=True, verbose_name="초대한 계정의 공개 ID"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="가입한 시각"),
                ),
            ],
            options={
                "verbose_name": "초대",
                "verbose_name_plural": "초대",
            },
        ),
        migrations.CreateModel(
            name="InviteCode",
            fields=[
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="invite_code",
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="계정",
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        max_length=8, unique=True, verbose_name="초대 코드"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="만든 시각"),
                ),
            ],
            options={
                "verbose_name": "초대 코드",
                "verbose_name_plural": "초대 코드",
            },
        ),
        migrations.CreateModel(
            name="InviteReward",
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
                    "invitee_key",
                    models.CharField(
                        max_length=64, unique=True, verbose_name="초대받은 사람의 열쇠"
                    ),
                ),
                (
                    "inviter_key",
                    models.CharField(
                        db_index=True, max_length=64, verbose_name="초대한 사람의 열쇠"
                    ),
                ),
                (
                    "invitee_public_id",
                    models.UUIDField(verbose_name="초대받은 계정의 공개 ID"),
                ),
                (
                    "inviter_public_id",
                    models.UUIDField(
                        db_index=True, verbose_name="초대한 계정의 공개 ID"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="정한 시각"),
                ),
            ],
            options={
                "verbose_name": "초대 보상",
                "verbose_name_plural": "초대 보상",
            },
        ),
        migrations.CreateModel(
            name="InviteGrant",
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
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("inviter", "초대한 사람"),
                            ("invitee", "초대받은 사람"),
                        ],
                        max_length=10,
                        verbose_name="받는 사람",
                    ),
                ),
                (
                    "user_public_id",
                    models.UUIDField(verbose_name="받는 계정의 공개 ID"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "맡기기 전"),
                            ("granted", "지급됨"),
                            ("already_granted", "이미 받은 사용자"),
                            ("disabled", "결제 서버가 꺼 둠"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="상태",
                    ),
                ),
                (
                    "attempts",
                    models.PositiveIntegerField(default=0, verbose_name="시도 횟수"),
                ),
                (
                    "last_error",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="마지막 오류"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="만든 시각"),
                ),
                (
                    "next_attempt_at",
                    models.DateTimeField(verbose_name="다음 시도 시각"),
                ),
                (
                    "finished_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="끝난 시각"
                    ),
                ),
                (
                    "reward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grants",
                        to="accounts.invitereward",
                        verbose_name="초대 보상",
                    ),
                ),
            ],
            options={
                "verbose_name": "초대 보상 지급",
                "verbose_name_plural": "초대 보상 지급",
                "indexes": [
                    models.Index(
                        fields=["status", "next_attempt_at"],
                        name="accounts_invite_grant_due_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("reward", "role"), name="accounts_invite_grant_once"
                    )
                ],
            },
        ),
    ]
