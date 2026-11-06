# auth-server/accounts/migrations/0036_nickname_change.py

"""
본인이 닉네임을 바꾸는 것(accounts/nicknames.py). 마지막으로 바꾼 시각과, 버린 닉네임을 묶어 두는 표다.
있던 계정은 바꾼 적이 없는 것(빈 시각)으로 시작한다.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0035_app_token_client"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="nickname_changed_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="닉네임을 바꾼 시각"
            ),
        ),
        migrations.CreateModel(
            name="ReleasedNickname",
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
                    "nickname",
                    models.CharField(max_length=20, unique=True, verbose_name="닉네임"),
                ),
                (
                    "held_until",
                    models.DateTimeField(db_index=True, verbose_name="묶어 두는 끝"),
                ),
                (
                    "released_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="released_nicknames",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="버린 사람",
                    ),
                ),
            ],
            options={
                "verbose_name": "버린 닉네임",
                "verbose_name_plural": "버린 닉네임",
            },
        ),
    ]
