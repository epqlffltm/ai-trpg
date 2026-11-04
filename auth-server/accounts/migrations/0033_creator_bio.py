# auth-server/accounts/migrations/0033_creator_bio.py

"""
제작자로서의 소개(#992). 비어 있는 채로 시작한다.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0032_receipt_notices"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="bio",
            field=models.CharField(
                blank=True, default="", max_length=200, verbose_name="소개"
            ),
        ),
    ]
