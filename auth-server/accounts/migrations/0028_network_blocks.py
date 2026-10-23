# auth-server/accounts/migrations/0028_network_blocks.py

"""
가입, 로그인, 토큰 갱신을 막는 IP 주소나 대역(NetworkBlock, #638)을 만든다.

  - 대역(PostgreSQL cidr, 같은 대역은 한 줄), 사유, 푸는 시각, 막은 시각
  - 요청마다 푸는 시각이 지나지 않은 줄만 보므로 그 칸에 색인을 둔다

되돌리면 표가 사라지고 막아 둔 주소가 풀린다. 개발용 DB 에서만 되돌린다.
"""

import accounts.db_fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0027_withdrawal_chat'),
    ]

    operations = [
        migrations.CreateModel(
            name='NetworkBlock',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'network',
                    accounts.db_fields.CidrField(unique=True, verbose_name='주소 또는 대역'),
                ),
                ('note', models.CharField(max_length=200, verbose_name='사유')),
                ('expires_at', models.DateTimeField(verbose_name='푸는 시각')),
                (
                    'created_at',
                    models.DateTimeField(auto_now_add=True, verbose_name='막은 시각'),
                ),
            ],
            options={
                'verbose_name': 'IP 막기',
                'verbose_name_plural': 'IP 막기',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['expires_at'], name='accounts_network_block_exp_idx')],
            },
        ),
    ]
