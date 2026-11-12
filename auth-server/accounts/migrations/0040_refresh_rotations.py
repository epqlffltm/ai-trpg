# auth-server/accounts/migrations/0040_refresh_rotations.py

"""
refresh 토큰을 바꾼 기록(RefreshRotation)의 표를 만든다. 바꾼 답을 잃었을 때 모든 세션을 끊지 않으려는 것이다(accounts/tokens.py).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0039_inquiry_kinds"),
        ("token_blacklist", "0013_alter_blacklistedtoken_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="RefreshRotation",
            fields=[
                (
                    "token",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="rotation",
                        serialize=False,
                        to="token_blacklist.outstandingtoken",
                        verbose_name="바꾼 refresh 토큰",
                    ),
                ),
                ("rotated_at", models.DateTimeField(verbose_name="처음 바꾼 시각")),
                (
                    "successor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="token_blacklist.outstandingtoken",
                        verbose_name="바꿔 준 refresh 토큰",
                    ),
                ),
            ],
            options={
                "verbose_name": "refresh 토큰을 바꾼 기록",
                "verbose_name_plural": "refresh 토큰을 바꾼 기록",
            },
        ),
    ]
