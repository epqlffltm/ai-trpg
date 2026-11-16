# auth-server/accounts/migrations/0041_remove_ai_training_consent.py

"""
동의 항목에서 대화 기록의 AI 학습 이용(ai_training)을 뺀다. 고르는 값(choices)만 바뀌어 DB 의 표는 그대로다.
그 값으로 남은 옛 기록은 지우지 않는다(동의 기록은 쌓기만 한다).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0040_refresh_rotations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="consentrecord",
            name="item",
            field=models.CharField(
                choices=[
                    ("terms", "이용약관"),
                    ("privacy", "개인정보 수집·이용"),
                    ("marketing", "마케팅 정보 수신"),
                ],
                max_length=32,
                verbose_name="항목",
            ),
        ),
    ]
