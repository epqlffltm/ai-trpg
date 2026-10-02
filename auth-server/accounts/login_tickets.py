# auth-server/accounts/login_tickets.py

"""
로그인 티켓의 발급과 확인.

로그인은 두 번의 요청으로 이루어진다(비밀번호 확인 → 이메일 코드 확인).
티켓은 두 번째 요청을 보낸 쪽이 첫 번째 요청에서 비밀번호를 통과한 쪽임을 증명한다.
티켓이 없으면 아이디만 아는 제3자가 틀린 코드를 보내 남의 코드를 폐기시킬 수 있다.

티켓만으로는 로그인할 수 없다. 메일로 받은 코드가 더 필요하다.
DB 에 저장하지 않는다. 서버의 비밀키로 서명해, 위조와 만료를 서명만으로 판단한다.
"""

from datetime import timedelta

from django.core import signing
from django.core.exceptions import ValidationError

from accounts.models import User

# 서명에 섞는 값. 같은 비밀키로 만든 다른 용도의 서명을 티켓으로 쓸 수 없게 한다
LOGIN_TICKET_SALT = 'accounts.login_ticket'

# 코드의 유효 시간(5분)보다 길게 잡는다. 코드를 한 번 다시 받을 여유를 둔다
LOGIN_TICKET_LIFETIME = timedelta(minutes=10)


class InvalidLoginTicketError(Exception):
    """
    티켓이 위조됐거나, 만료됐거나, 더는 로그인할 수 없는 계정의 것이다.

    이유를 구분하지 않는다. 어느 경우든 로그인을 처음부터 다시 해야 한다.
    """


def issue_login_ticket(user: User) -> str:
    """비밀번호 확인을 통과한 사용자에게 줄 티켓을 만든다."""
    payload = {
        'sub': str(user.public_id),
        # 세션 버전을 담는다. 모든 기기 로그아웃이나 비밀번호 변경 뒤에는
        # 그 전에 받은 티켓으로 로그인을 이어 갈 수 없다
        'ver': user.token_version,
    }
    return signing.dumps(payload, salt=LOGIN_TICKET_SALT)


def read_login_ticket(ticket: str) -> User:
    """티켓을 확인하고 그 주인을 돌려준다. 쓸 수 없는 티켓이면 InvalidLoginTicketError 를 낸다."""
    payload = _load_payload(ticket)
    user = _find_user(payload)
    _ensure_can_continue_login(user, payload)
    return user


def _load_payload(ticket: str) -> dict:
    try:
        payload = signing.loads(ticket, salt=LOGIN_TICKET_SALT, max_age=LOGIN_TICKET_LIFETIME)
    except signing.BadSignature as exc:
        # 만료(SignatureExpired)도 BadSignature 의 한 종류다
        raise InvalidLoginTicketError from exc
    if not isinstance(payload, dict):
        raise InvalidLoginTicketError
    return payload


def _find_user(payload: dict) -> User:
    try:
        return User.objects.get(public_id=payload.get('sub'))
    except (User.DoesNotExist, ValidationError) as exc:
        # sub 가 UUID 모양이 아니면 ValidationError 가 난다
        raise InvalidLoginTicketError from exc


def _ensure_can_continue_login(user: User, payload: dict) -> None:
    """티켓을 받은 뒤에 계정 상태가 바뀌었으면 거부한다."""
    if not user.is_active:
        raise InvalidLoginTicketError
    if payload.get('ver') != user.token_version:
        raise InvalidLoginTicketError