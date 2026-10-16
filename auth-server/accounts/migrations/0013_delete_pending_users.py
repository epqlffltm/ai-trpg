# auth-server/accounts/migrations/0013_delete_pending_users.py

"""
옛 가입 흐름이 남긴 미인증 계정을 지운다(#271).

옛 흐름은 이메일을 확인하기 전에 계정을 만들고, 코드가 맞으면 인증된 것으로 바꿨다.
새 흐름은 이메일을 먼저 확인하고 그 뒤에 인증된 계정을 바로 만든다. 옛 계정을 인증할 길(옛 signup/verify)은 없어졌다.
남겨 두면 아이디, 닉네임, 이메일을 붙잡은 채 영영 쓸 수 없는 계정이 된다. 옛 흐름에서도 1시간이 지나면 지우던 계정이다.

관리자가 만든 계정(createsuperuser)은 처음부터 인증된 것이라 지우지 않는다.
딸린 것: 인증 코드는 함께 지워지고(CASCADE), 보안 이벤트는 계정만 비운다(SET_NULL).
"""

from django.db import migrations


def delete_pending_users(apps, schema_editor):
    # 이 마이그레이션 시점의 모델 모양을 쓴다(0006 과 같다)
    User = apps.get_model('accounts', 'User')
    User.objects.filter(email_verified_at__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_signupcode'),
    ]

    operations = [
        # 되돌릴 때는 아무것도 하지 않는다. 지운 계정은 되살릴 수 없고, 되살려도 인증할 길이 없다
        migrations.RunPython(delete_pending_users, migrations.RunPython.noop),
    ]
