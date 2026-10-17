# auth-server/accounts/backoff.py

"""
실패한 뒤 다시 시도하기까지 기다릴 시간.
결제 서버에 맡기는 두 일(welcome_credit.py, payment_eligibility.py)이 함께 쓴다.

실패할 때마다 두 배가 되고(5초, 10초, 20초, ...) 정한 데서 멈춘다. 상대가 죽어 있을 때 쉬지 않고 두드리지 않는다.
"""

from datetime import timedelta

# 간격이 늘어나는 실패의 횟수. 그 뒤로는 2 의 거듭제곱을 더 키우지 않는다. 큰 수의 거듭제곱을 만들지 않으려는 것이다
_MAX_DOUBLINGS = 10


def retry_delay(attempts: int, *, first: timedelta, maximum: timedelta) -> timedelta:
    """attempts 번 실패한 뒤에 기다릴 시간. 첫 실패 뒤가 first 이고 maximum 을 넘지 않는다."""
    doublings = min(attempts - 1, _MAX_DOUBLINGS)
    return min(first * (2**doublings), maximum)
