# auth-server/accounts/signup_tickets.py

"""
가입 티켓의 발급과 확인(#271).

가입은 세 번의 요청이다(이메일 → 코드 → 아이디와 비밀번호).
티켓은 세 번째 요청을 보낸 쪽이 두 번째 요청에서 그 이메일의 코드를 맞힌 쪽임을 증명한다.
그래서 가입 내용(아이디, 닉네임, 비밀번호)은 이메일의 주인이 코드를 받은 뒤에만 정할 수 있다.

DB 에 저장하지 않는다. 서버의 비밀키로 서명해, 위조와 만료를 서명만으로 판단한다(로그인 티켓과 같다).
한 번만 쓰이는 것은 DB 가 지킨다. 같은 이메일의 계정은 하나뿐이라(대소문자 무시의 유일 제약)
두 번째 가입은 저장에서 막힌다.
"""

from datetime import timedelta

from django.core import signing

# 서명에 섞는 값. 같은 비밀키로 만든 다른 용도의 서명(로그인 티켓)을 가입 티켓으로 쓸 수 없게 한다
SIGNUP_TICKET_SALT = 'accounts.signup_ticket'

# 코드를 맞힌 뒤 아이디와 비밀번호를 정하는 데 쓰는 시간. 비밀번호 규칙에 걸려 몇 번 고쳐 쓸 여유를 둔다
SIGNUP_TICKET_LIFETIME = timedelta(minutes=30)


class InvalidSignupTicketError(Exception):
    """
    티켓이 위조됐거나 만료됐다.

    이유를 구분하지 않는다. 어느 경우든 가입을 처음(이메일)부터 다시 해야 한다.
    """


def issue_signup_ticket(email: str) -> str:
    """코드를 맞힌 이메일에 줄 티켓을 만든다."""
    return signing.dumps({'email': email.lower()}, salt=SIGNUP_TICKET_SALT)


def read_signup_ticket(ticket: str) -> str:
    """티켓을 확인하고 그 이메일을 돌려준다. 쓸 수 없는 티켓이면 InvalidSignupTicketError 를 낸다."""
    payload = _load_payload(ticket)
    email = payload.get('email')
    if not isinstance(email, str) or not email:
        raise InvalidSignupTicketError
    return email


def _load_payload(ticket: str) -> dict:
    try:
        payload = signing.loads(ticket, salt=SIGNUP_TICKET_SALT, max_age=SIGNUP_TICKET_LIFETIME)
    except signing.BadSignature as exc:
        # 만료(SignatureExpired)도 BadSignature 의 한 종류다
        raise InvalidSignupTicketError from exc
    if not isinstance(payload, dict):
        raise InvalidSignupTicketError
    return payload
