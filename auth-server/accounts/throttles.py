# auth-server/accounts/throttles.py

"""
IP 별 시도 제한을 DRF 의 throttle 로 건다. 뷰에는 throttle_classes 한 줄만 적는다.

throttle 은 뷰가 실행되기 전에 돈다. 그래서 "성공이든 실패든 모든 시도를 센다" 에만 쓴다.
비밀번호가 틀렸을 때만 세는 제한은 결과를 알아야 하므로 뷰가 직접 센다(attempt_policies.py).

DRF 에 들어 있는 SimpleRateThrottle 은 쓰지 않는다.
  - 횟수를 읽고 쓰는 것이 따로라서, 동시에 온 요청이 같은 횟수를 읽고 함께 통과한다.
  - 캐시가 죽으면 예외가 그대로 올라가 500 이 된다. 우리는 Redis 가 죽으면 통과시키기로 했다.
세는 일은 attempt_limits.py 에 맡기고, 여기는 DRF 와 이어 주기만 한다.
"""

from rest_framework.request import Request
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from accounts.attempt_limits import AttemptLimit, TooManyAttemptsError, count_attempt
from accounts.attempt_policies import (
    LOGIN_PER_IP,
    PASSWORD_RESET_PER_IP,
    SIGNUP_PER_IP,
    SIGNUP_RESEND_PER_IP,
)
from accounts.client_ip import get_attempt_subject


class IpAttemptThrottle(BaseThrottle):
    """
    한 IP 의 시도를 limit 만큼만 허용한다. 물려받는 쪽이 limit 을 정한다.

    DRF 는 allow_request 가 False 를 돌려주면 wait 를 불러 기다릴 시간을 묻고, 429 로 응답한다.
    """

    limit: AttemptLimit

    def allow_request(self, request: Request, view: APIView) -> bool:
        try:
            count_attempt(self.limit, get_attempt_subject(request))
        except TooManyAttemptsError as exc:
            self.retry_after = exc.retry_after
            return False
        return True

    def wait(self) -> float:
        return self.retry_after.total_seconds()


class LoginIpThrottle(IpAttemptThrottle):
    limit = LOGIN_PER_IP


class SignupIpThrottle(IpAttemptThrottle):
    limit = SIGNUP_PER_IP


class SignupResendIpThrottle(IpAttemptThrottle):
    limit = SIGNUP_RESEND_PER_IP


class PasswordResetIpThrottle(IpAttemptThrottle):
    limit = PASSWORD_RESET_PER_IP
