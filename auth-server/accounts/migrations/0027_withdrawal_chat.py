# auth-server/accounts/migrations/0027_withdrawal_chat.py

"""
탈퇴를 알릴 서버에 chat 을 더한다(#670). 선택지만 바뀐다. DB 의 칸은 그대로다.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0026_return_blocks"),
    ]

    operations = [
        migrations.AlterField(
            model_name="withdrawalnotice",
            name="target",
            field=models.CharField(
                choices=[
                    ("billing", "결제 서버"),
                    ("notification", "알림 서버"),
                    ("game", "게임 서버"),
                    ("board", "게시판 서버"),
                    ("asset", "asset 서버"),
                    ("chat", "chat 서버"),
                ],
                max_length=32,
                verbose_name="알릴 서버",
            ),
        ),
    ]
