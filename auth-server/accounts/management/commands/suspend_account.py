# auth-server/accounts/management/commands/suspend_account.py

"""
계정을 정지하는 관리 명령(#274).

    uv run python manage.py suspend_account <아이디> --reason "<사유>"

로그인과 refresh 를 막고, 이미 발급된 토큰을 끊는다. 다른 서버에서도 30초 안에 막힌다(accounts/suspension.py).
사유는 보안 이벤트에 남는다. 비밀번호나 이메일 주소 같은 것을 적지 않는다.
"""

from django.core.management.base import BaseCommand, CommandError

from accounts.suspension import InvalidNoteError, UnknownAccountError, clean_note, find_account, suspend_account


class Command(BaseCommand):
    help = '계정을 정지한다. 이미 발급된 토큰도 끊는다.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('username', help='정지할 계정의 아이디')
        parser.add_argument('--reason', required=True, help='정지하는 사유. 보안 이벤트에 남는다')

    def handle(self, *args, **options) -> None:
        try:
            note = clean_note(options['reason'])
            user = find_account(options['username'])
        except InvalidNoteError as exc:
            raise CommandError(str(exc)) from exc
        except UnknownAccountError as exc:
            raise CommandError('그런 아이디의 계정이 없습니다.') from exc

        if suspend_account(user, note):
            self.stdout.write(f'{user.username} 를 정지했습니다. 다른 서버에서도 30초 안에 막힙니다.')
        else:
            self.stdout.write(f'{user.username} 는 이미 정지된 계정입니다. 바꾼 것이 없습니다.')
