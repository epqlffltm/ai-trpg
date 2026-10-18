# auth-server/accounts/migrations/0019_operators_group.py

"""
운영자의 그룹 operators 를 만든다(#389).

그룹에 든 계정의 access 토큰에 roles: ["operator"] 가 실린다(accounts/roles.py).
그룹에는 Django 의 권한(permission)을 붙이지 않는다. 관리자 화면의 권한과 나누려는 것이다.
되돌리면 그룹과 그 안의 소속이 지워진다. 그 뒤로 발급되는 토큰에는 운영자가 없다.
"""

from django.db import migrations

# 이 마이그레이션 시점의 이름을 적는다. accounts/roles.py 의 상수를 가져오지 않는다(나중에 바뀌어도 이 파일은 그대로다)
OPERATORS_GROUP = 'operators'


def create_operators_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name=OPERATORS_GROUP)


def delete_operators_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name=OPERATORS_GROUP).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_guardian_notices'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_operators_group, delete_operators_group),
    ]
