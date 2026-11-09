# auth-server/support/throttles.py

"""
문의 보내기의 IP 별 시도 제한. 로그인하지 않고도 보낼 수 있어서, 같은 곳에서 문의를 쏟아붓는 것을 늦춘다.
세는 일과 막을 때의 보안 이벤트는 accounts 의 시도 제한과 같다(accounts/throttles.py).
"""

from datetime import timedelta

from accounts.attempt_limits import AttemptLimit
from accounts.models import SecurityEventKind
from accounts.throttles import IpAttemptThrottle

# 한 IP 가 한 시간에 보낼 수 있는 문의의 수. 한 사람이 급히 여러 번 보내도 막히지 않을 만큼이다
INQUIRY_PER_IP = AttemptLimit(name='inquiry-ip', max_attempts=5, window=timedelta(hours=1))


class InquiryIpThrottle(IpAttemptThrottle):
    limit = INQUIRY_PER_IP
    event_kind = SecurityEventKind.INQUIRY_IP_LIMITED
