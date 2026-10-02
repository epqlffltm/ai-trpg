# auth-server/accounts/migrations/0006_mark_existing_users_verified.py

"""
이메일 인증이 생기기 전에 만든 계정을 인증된 것으로 표시한다.

0005 에서 email_verified_at 이 추가되면서 기존 계정은 전부 값이 비어 있다.
그대로 두면 관리자 계정을 포함한 기존 계정이 모두 로그인할 수 없게 된다.

스키마가 아니라 데이터를 바꾸는 마이그레이션이다. makemigrations 가 만들어 주지 않으므로 직접 쓴다.
"""

from django.db import migrations
from django.db.models import F


def mark_existing_users_verified(apps, schema_editor):
    # 지금의 User 클래스를 import 하지 않는다.
    # 이 마이그레이션 시점의 모델 모양은 apps.get_model 로 얻어야 한다.
    # 나중에 User 에 필드가 더 생겨도 이 마이그레이션은 그대로 돌아간다
    User = apps.get_model('accounts', 'User')
    User.objects.filter(email_verified_at__isnull=True).update(
        email_verified_at=F('date_joined'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_alter_user_managers_user_email_verified_at'),
    ]

    operations = [
        # 되돌릴 때는 아무것도 하지 않는다. 0005 를 되돌리면 열 자체가 사라진다
        migrations.RunPython(mark_existing_users_verified, migrations.RunPython.noop),
    ]