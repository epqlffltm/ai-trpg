# auth-server/accounts/withdrawal_schedule.py

"""
탈퇴의 유예와 그 끝(#603). 토큰을 만드는 쪽(tokens.py)과 탈퇴를 다루는 쪽(withdrawal.py)이 함께 읽는다.

withdrawal.py 는 세션을 끊으려고 tokens.py 를 부른다. tokens.py 가 withdrawal.py 를 부르면 서로를 부르게 되어
유예의 규칙만 여기에 따로 둔다.
"""

from datetime import datetime, timedelta

from accounts.models import User

# 탈퇴를 요청한 뒤 계정을 비우기까지의 시간(유저 결정, 2026-10-21). 그 안에 다시 로그인해 취소한다.
# 도용된 계정이나 실수로 누른 것을 살릴 시간이다
GRACE = timedelta(days=7)


def withdrawal_scheduled_at(user: User) -> datetime | None:
    """
    그 계정을 비울 시각. 탈퇴를 요청하지 않았거나, 취소했거나, 이미 마쳤으면 None 이다.

    값이 있으면 그 계정은 유예 중이다. 그동안의 access 토큰은 인증 서버에만 통한다(tokens.py 의 audience_for).
    """
    if user.withdrawal_requested_at is None or user.withdrawn_at is not None:
        return None
    return user.withdrawal_requested_at + GRACE
