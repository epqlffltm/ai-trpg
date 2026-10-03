# auth-server/accounts/security_events.py

"""
보안 이벤트를 기록한다.

기록할지 말지는 부르는 쪽이 정한다. 여기는 적기만 한다.
막힌 뒤에도 계속 들어오는 요청마다 적으면, 공격자가 요청 수만큼 DB 에 행을 쌓을 수 있다.
그래서 부르는 쪽은 "막히기 시작한 순간" 에만 부른다(attempt_limits 가 그 순간을 알려 준다).
"""

from accounts.models import SecurityEvent, User


def record_security_event(*, kind: str, ip: str = '', user: User | None = None) -> None:
    """보안 이벤트 하나를 남긴다."""
    SecurityEvent.objects.create(kind=kind, ip=ip, user=user)


def find_user_by_username(username: str) -> User | None:
    """
    로그인에 입력된 아이디의 주인을 찾는다. 없으면 None 이다.

    이벤트에 대상 계정을 적기 위해서만 쓴다. 로그인 판정에는 쓰지 않는다.
    """
    return User.objects.filter(username=username.strip()).first()
