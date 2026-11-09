# auth-server/support/migrations/0002_inquiry_read_at.py

"""
운영자가 문의를 처음 연 시각(read_at). 운영자 화면이 메일함처럼 읽지 않은 문의를 가른다.
이미 있는 문의는 비어 있다(읽지 않은 것으로 보인다).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("support", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="inquiry",
            name="read_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="운영자가 읽은 시각"
            ),
        ),
    ]
