# auth-server/accounts/management/commands/unblock_network.py

"""
block_network 로 막은 IP 주소나 대역을 푸는 관리 명령(#638).

    uv run python manage.py unblock_network <주소 또는 대역>

막을 때와 같은 규칙으로 대역을 정한다(주소 하나는 IPv4 /32, IPv6 /64). 막을 때 적은 것과 같은 대역이어야 풀린다.
관리 화면에서 그 줄을 지워도 같다.
"""

from django.core.management.base import BaseCommand, CommandError

from accounts.network_blocks import InvalidNetworkError, parse_network, unblock_network


class Command(BaseCommand):
    help = '막은 IP 주소나 대역을 푼다.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('network', help='풀 IP 주소나 대역')

    def handle(self, *args, **options) -> None:
        try:
            network = parse_network(options['network'])
        except InvalidNetworkError as exc:
            raise CommandError(str(exc)) from exc

        if unblock_network(network):
            self.stdout.write(f'{network} 를 풀었습니다.')
        else:
            self.stdout.write(f'{network} 를 막은 줄이 없습니다. 바꾼 것이 없습니다.')
