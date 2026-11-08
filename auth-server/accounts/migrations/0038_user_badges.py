# auth-server/accounts/migrations/0038_user_badges.py

"""
활동 배지(#193, accounts/badges.py). 받은 배지의 표를 만들고, 이미 있는 기록으로 받았어야 할 배지를 채운다.

채우는 것: 본인인증, 첫 초대(초대 보상을 받은 초대한 계정), 출석의 배지 넷(첫 출석, 한 주기 완주, 출석 30일, 용의 보물).
받은 시각은 그 일이 적힌 시각이다. 되돌리면 표가 지워진다. 기록은 그대로라 다시 적용하면 같게 채운다.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# 이 마이그레이션 시점의 이름을 적는다. accounts/badge_rules.py 의 상수를 가져오지 않는다(나중에 바뀌어도 이 파일은 그대로다)
IDENTITY_VERIFIED = 'identity_verified'
FIRST_INVITE = 'first_invite'
FIRST_ATTENDANCE = 'first_attendance'
ATTENDANCE_CYCLE = 'attendance_cycle'
ATTENDANCE_30_DAYS = 'attendance_30_days'
DRAGON_HOARD = 'dragon_hoard'
ATTENDANCE_DAYS_GOAL = 30


def _identity_badges(apps):
    """본인인증을 마친 계정마다 하나."""
    IdentityVerification = apps.get_model('accounts', 'IdentityVerification')
    UserBadge = apps.get_model('accounts', 'UserBadge')
    return [
        UserBadge(user_id=user_id, badge=IDENTITY_VERIFIED, earned_at=verified_at)
        for user_id, verified_at in IdentityVerification.objects.values_list('user_id', 'verified_at')
    ]


def _invite_badges(apps):
    """초대 보상을 받은, 지금 있는 초대한 계정마다 하나. 받은 시각은 처음 보상의 시각이다."""
    InviteReward = apps.get_model('accounts', 'InviteReward')
    User = apps.get_model('accounts', 'User')
    UserBadge = apps.get_model('accounts', 'UserBadge')
    first = (
        InviteReward.objects.values('inviter_public_id')
        .annotate(first_at=models.Min('created_at'))
        .values_list('inviter_public_id', 'first_at')
    )
    users = dict(User.objects.filter(public_id__in=[public_id for public_id, _ in first]).values_list('public_id', 'id'))
    return [
        UserBadge(user_id=users[public_id], badge=FIRST_INVITE, earned_at=first_at)
        for public_id, first_at in first
        if public_id in users
    ]


def _first_claims(apps, badge, **conditions):
    """그 조건에 맞는 첫 출석의 시각으로, 사용자마다 그 배지 하나."""
    AttendanceClaim = apps.get_model('accounts', 'AttendanceClaim')
    UserBadge = apps.get_model('accounts', 'UserBadge')
    first = (
        AttendanceClaim.objects.filter(**conditions)
        .values('user_id')
        .annotate(first_at=models.Min('created_at'))
        .values_list('user_id', 'first_at')
    )
    return [UserBadge(user_id=user_id, badge=badge, earned_at=first_at) for user_id, first_at in first]


def _thirty_days_badges(apps):
    """출석한 날이 30일이 된 사용자마다 하나. 받은 시각은 30번째 출석의 시각이다."""
    AttendanceClaim = apps.get_model('accounts', 'AttendanceClaim')
    UserBadge = apps.get_model('accounts', 'UserBadge')
    reached = (
        AttendanceClaim.objects.values('user_id')
        .annotate(days=models.Count('id'))
        .filter(days__gte=ATTENDANCE_DAYS_GOAL)
        .values_list('user_id', flat=True)
    )
    badges = []
    for user_id in reached:
        claim = AttendanceClaim.objects.filter(user_id=user_id).order_by('day')[ATTENDANCE_DAYS_GOAL - 1]
        badges.append(UserBadge(user_id=user_id, badge=ATTENDANCE_30_DAYS, earned_at=claim.created_at))
    return badges


def fill_badges(apps, schema_editor):
    UserBadge = apps.get_model('accounts', 'UserBadge')
    badges = [
        *_identity_badges(apps),
        *_invite_badges(apps),
        *_first_claims(apps, FIRST_ATTENDANCE),
        *_first_claims(apps, ATTENDANCE_CYCLE, chest_table__isnull=False),
        *_first_claims(apps, DRAGON_HOARD, chest_outcome='dragon_hoard'),
        *_thirty_days_badges(apps),
    ]
    UserBadge.objects.bulk_create(badges, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0037_attendance'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserBadge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('badge', models.CharField(max_length=40, verbose_name='배지')),
                ('earned_at', models.DateTimeField(verbose_name='받은 시각')),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='badges',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='받은 사람',
                    ),
                ),
            ],
            options={
                'verbose_name': '활동 배지',
                'verbose_name_plural': '활동 배지',
                'constraints': [models.UniqueConstraint(fields=('user', 'badge'), name='accounts_badge_once')],
            },
        ),
        # 되돌릴 때는 표가 지워지므로 따로 할 일이 없다
        migrations.RunPython(fill_badges, migrations.RunPython.noop),
    ]
