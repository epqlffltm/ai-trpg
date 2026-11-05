# auth-server/accounts/migrations/0035_app_token_client.py

"""
발급한 refresh 토큰을 웹과 앱 가운데 어디에 줬는지(#429). 토큰 하나에 한 줄이다.
이 표를 만들기 전에 발급된 토큰은 줄이 없고 웹의 것으로 본다(accounts/tokens.py 의 client_of).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0034_blocks"),
        ("token_blacklist", "0013_alter_blacklistedtoken_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="IssuedTokenClient",
            fields=[
                (
                    "token",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="client_record",
                        serialize=False,
                        to="token_blacklist.outstandingtoken",
                        verbose_name="발급한 refresh 토큰",
                    ),
                ),
                (
                    "client",
                    models.CharField(
                        choices=[
                            ("web", "웹(httpOnly 쿠키)"),
                            ("app", "앱(응답 본문)"),
                        ],
                        max_length=8,
                        verbose_name="준 곳",
                    ),
                ),
            ],
            options={
                "verbose_name": "토큰을 준 곳",
                "verbose_name_plural": "토큰을 준 곳",
            },
        ),
    ]
