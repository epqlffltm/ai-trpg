# auth-server/accounts/management/commands/suspend_account.py

"""
계정을 정지하는 관리 명령(#274).

    uv run python manage.py suspend_account <아이디> --kind <사유의 종류> --reason "<사유>"

로그인과 refresh 를 막고, 이미 발급된 토큰을 끊는다. 다른 서버에서도 30초 안에 막힌다(accounts/suspension.py).
사유의 종류는 spam, abuse, fraud, illegal, other 가운데 하나다(accounts.models.SuspensionReason).
정지된 채 탈퇴한 사람이 다시 가입할 때 무엇을 막을지가 종류마다 다르다(#634).
사유는 정지의 기록과 보안 이벤트에 남는다. 비밀번호나 이메일 주소 같은 것을 적지 않는다.
"""

from django.core.management.base import BaseCommand, CommandError

from accounts.models import SuspensionReason
from accounts.suspension import (
    InvalidNoteError,
    UnknownAccountError,
    UnknownReasonError,
    clean_note,
    clean_reason,
    find_account,
    suspend_account,
)


class Command(BaseCommand):
    help = '계정을 정지한다. 이미 발급된 토큰도 끊는다.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('username', help='정지할 계정의 아이디')
        parser.add_argument('--kind', required=True, help=f'사유의 종류: {", ".join(SuspensionReason.values)}')
        parser.add_argument('--reason', required=True, help='정지하는 사유. 정지의 기록과 보안 이벤트에 남는다')

    def handle(self, *args, **options) -> None:
        try:
            reason = clean_reason(options['kind'])
            note = clean_note(options['reason'])
            user = find_account(options['username'])
        except UnknownReasonError as exc:
            raise CommandError(f'사유의 종류는 {", ".join(SuspensionReason.values)} 가운데 하나입니다.') from exc
        except InvalidNoteError as exc:
            raise CommandError(str(exc)) from exc
        except UnknownAccountError as exc:
            raise CommandError('그런 아이디의 계정이 없습니다.') from exc

        if suspend_account(user, note, reason=reason):
            self.stdout.write(f'{user.username} 를 정지했습니다. 다른 서버에서도 30초 안에 막힙니다.')
        else:
            self.stdout.write(f'{user.username} 는 이미 정지된 계정입니다. 바꾼 것이 없습니다.')
