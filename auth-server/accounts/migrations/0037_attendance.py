# auth-server/accounts/migrations/0037_attendance.py

"""
출석(accounts/attendance.py). 결제 서버에서 옮겨 온 출석의 기록이자 결제 서버에 실버를 맡길 일이다.
결제 서버의 옛 출석 기록은 옮기지 않는다. 처음부터 새로 센다(2026-11-08 결정).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0036_nickname_change"),
    ]

    operations = [
        migrations.CreateModel(
            name="AttendanceClaim",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("day", models.DateField(verbose_name="출석한 날")),
                (
                    "cycle_day",
                    models.PositiveSmallIntegerField(verbose_name="주기의 며칠째"),
                ),
                ("silver", models.PositiveIntegerField(verbose_name="하루 양")),
                (
                    "chest_table",
                    models.CharField(
                        blank=True,
                        max_length=20,
                        null=True,
                        verbose_name="상자의 확률표",
                    ),
                ),
                (
                    "chest_outcome",
                    models.CharField(
                        blank=True, max_length=40, null=True, verbose_name="상자의 결과"
                    ),
                ),
                (
                    "chest_silver",
                    models.PositiveIntegerField(default=0, verbose_name="상자의 실버"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "맡기기 전"),
                            ("granted", "지급됨"),
                            ("already_granted", "이미 받은 사용자"),
                            ("disabled", "결제 서버가 꺼 둠"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="상태",
                    ),
                ),
                (
                    "attempts",
                    models.PositiveIntegerField(default=0, verbose_name="시도 횟수"),
                ),
                (
                    "last_error",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="마지막 오류"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="출석한 시각"),
                ),
                (
                    "next_attempt_at",
                    models.DateTimeField(verbose_name="다음 시도 시각"),
                ),
                (
                    "finished_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="끝난 시각"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_claims",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="출석한 사람",
                    ),
                ),
            ],
            options={
                "verbose_name": "출석",
                "verbose_name_plural": "출석",
                "indexes": [
                    models.Index(
                        fields=["status", "next_attempt_at"],
                        name="accounts_attendance_due_idx",
                    ),
                    models.Index(
                        fields=["user", "-day"], name="accounts_attendance_last_idx"
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "day"), name="accounts_attendance_once_a_day"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("cycle_day__gte", 1)),
                        name="accounts_attendance_cycle_day_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("chest_outcome__isnull", True),
                                ("chest_silver", 0),
                                ("chest_table__isnull", True),
                            ),
                            models.Q(
                                ("chest_outcome__isnull", False),
                                ("chest_table__isnull", False),
                            ),
                            _connector="OR",
                        ),
                        name="accounts_attendance_chest_complete",
                    ),
                ],
            },
        ),
    ]
