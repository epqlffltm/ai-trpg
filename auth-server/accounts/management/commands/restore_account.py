# auth-server/accounts/management/commands/restore_account.py

"""
계정의 정지를 푸는 관리 명령(#274).

    uv run python manage.py restore_account <아이디> --reason "<사유>"

다시 로그인할 수 있게 한다. 정지 전의 토큰은 되살리지 않는다. 사용자는 다시 로그인한다.
"""

from django.core.management.base import BaseCommand, CommandError

from accounts.suspension import InvalidNoteError, UnknownAccountError, clean_note, find_account, restore_account


class Command(BaseCommand):
    help = '계정의 정지를 푼다.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('username', help='정지를 풀 계정의 아이디')
        parser.add_argument('--reason', required=True, help='정지를 푸는 사유. 보안 이벤트에 남는다')

    def handle(self, *args, **options) -> None:
        try:
            note = clean_note(options['reason'])
            user = find_account(options['username'])
        except InvalidNoteError as exc:
            raise CommandError(str(exc)) from exc
        except UnknownAccountError as exc:
            raise CommandError('그런 아이디의 계정이 없습니다.') from exc

        if restore_account(user, note):
            self.stdout.write(f'{user.username} 의 정지를 풀었습니다.')
        else:
            self.stdout.write(f'{user.username} 는 정지된 계정이 아닙니다. 바꾼 것이 없습니다.')
