# auth-server/accounts/migrations/0031_content_settings.py

"""
목록을 거르는 내 설정(#986, #987). 성인 작품 표시(처음에는 켜짐)와 성향(처음에는 전체).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0030_invites"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="orientation",
            field=models.CharField(
                choices=[("all", "전체"), ("male", "남성향"), ("female", "여성향")],
                default="all",
                max_length=10,
                verbose_name="성향",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="show_adult_content",
            field=models.BooleanField(default=True, verbose_name="성인 작품 표시"),
        ),
    ]
