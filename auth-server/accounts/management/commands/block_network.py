# auth-server/accounts/management/commands/block_network.py

"""
IP 주소나 대역에서 오는 가입, 로그인, 토큰 갱신을 막는 관리 명령(#638).

    uv run python manage.py block_network <주소 또는 대역> --reason "<사유>" [--days <일>]

주소 하나는 IPv4 면 그 주소, IPv6 면 그 주소가 든 /64 를 막는다. 대역은 1.2.3.0/24 꼴로 적는다.
IPv4 /16, IPv6 /32 보다 넓게는 막지 않는다. 기간은 기본 30일, 길어야 365일이다(accounts/network_blocks.py).
같은 대역을 다시 막으면 기간과 사유를 이번 것으로 바꾼다. 다른 서버는 지금의 access 토큰이 끝나면 끊긴다.
사유에는 사람의 이름이나 이메일 주소를 적지 않는다. 푸는 것은 unblock_network 다.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.network_blocks import (
    DEFAULT_DAYS,
    InvalidDaysError,
    InvalidNetworkError,
    block_network,
    clean_days,
    parse_network,
)
from accounts.suspension import InvalidNoteError, clean_note


class Command(BaseCommand):
    help = 'IP 주소나 대역에서 오는 가입, 로그인, 토큰 갱신을 기간을 두고 막는다.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('network', help='막을 IP 주소나 대역(1.2.3.4, 1.2.3.0/24, 2001:db8::1)')
        parser.add_argument('--reason', required=True, help='막는 사유. 관리 화면에 남는다')
        parser.add_argument('--days', type=int, default=DEFAULT_DAYS, help=f'막는 기간(일). 기본 {DEFAULT_DAYS}')

    def handle(self, *args, **options) -> None:
        try:
            network = parse_network(options['network'])
            days = clean_days(options['days'])
            note = clean_note(options['reason'])
        except (InvalidNetworkError, InvalidDaysError, InvalidNoteError) as exc:
            raise CommandError(str(exc)) from exc

        block, created = block_network(network, days, note, timezone.now())
        until = timezone.localtime(block.expires_at).strftime('%Y-%m-%d %H:%M')
        if created:
            self.stdout.write(f'{network} 를 {until} 까지 막았습니다.')
        else:
            self.stdout.write(f'{network} 는 이미 막혀 있었습니다. {until} 까지로 바꿨습니다.')
