# auth-server/accounts/migrations/0034_blocks.py

"""
막은 제작자와 태그(#988). 한 사람이 막은 것 하나가 한 줄이다. 같은 것을 두 번 막지 않는다.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0033_creator_bio"),
    ]

    operations = [
        migrations.CreateModel(
            name="CreatorBlock",
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
                (
                    "creator_public_id",
                    models.UUIDField(
                        db_index=True, verbose_name="막은 제작자의 공개 ID"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="막은 시각"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="creator_blocks",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="막은 사람",
                    ),
                ),
            ],
            options={
                "verbose_name": "막은 제작자",
                "verbose_name_plural": "막은 제작자",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "creator_public_id"), name="uq_creator_block"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="TagBlock",
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
                ("tag", models.CharField(max_length=20, verbose_name="태그")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="막은 시각"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tag_blocks",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="막은 사람",
                    ),
                ),
            ],
            options={
                "verbose_name": "막은 태그",
                "verbose_name_plural": "막은 태그",
                "constraints": [
                    models.UniqueConstraint(fields=("user", "tag"), name="uq_tag_block")
                ],
            },
        ),
    ]
