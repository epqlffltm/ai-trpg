# auth-server/accounts/attempt_policies.py

"""
어느 API 에 어떤 시도 제한을 걸지 정한다. 숫자는 전부 여기 모여 있다.

세는 방법(Redis)은 attempt_limits.py 가, IP 를 알아내는 방법은 client_ip.py 가 안다.
여기는 "무엇을 기준으로, 몇 번까지" 만 정한다.

제한은 두 종류고, 거는 방법이 다르다.
  - 모든 시도를 센다(이름이 _PER_IP 로 끝난다): 한 IP 가 낼 수 있는 요청의 수를 묶는다. 성공해도 센다.
    결과를 몰라도 되므로 뷰가 실행되기 전에 throttle 이 센다(throttles.py).
  - 실패만 센다(이름에 FAILURES 가 있다): 비밀번호를 틀린 횟수를 묶는다. 성공하면 지운다.
    결과를 알아야 하므로 뷰가 이 파일의 함수를 직접 부른다.
"""

from datetime import timedelta

from accounts.attempt_limits import (
    AttemptLimit,
    clear_attempts,
    count_failure,
    ensure_not_blocked,
)
from accounts.models import User

# 한 IP 의 로그인 시도. 성공도 센다. 여러 계정을 돌아가며 찔러 보는 것을 늦춘다.
# 공유기 뒤의 여러 사람(학교, 회사)이 한 IP 로 보이므로 넉넉하게 잡는다
LOGIN_PER_IP = AttemptLimit(name='login-ip', max_attempts=30, window=timedelta(minutes=10))

# 한 IP 가 한 계정의 비밀번호를 틀린 횟수. 한 계정을 집중해서 맞히는 것을 막는다.
# 계정만으로 세지 않는다. 그러면 남의 아이디로 일부러 틀려 주인을 잠글 수 있다
LOGIN_FAILURES_PER_ACCOUNT_AND_IP = AttemptLimit(
    name='login-fail-account-ip', max_attempts=5, window=timedelta(minutes=15),
)

# 한 IP 의 가입 요청. 가입은 메일을 보낸다. 남의 주소로 메일을 쏟아붓는 것을 막는다
SIGNUP_PER_IP = AttemptLimit(name='signup-ip', max_attempts=10, window=timedelta(hours=1))
SIGNUP_RESEND_PER_IP = AttemptLimit(name='signup-resend-ip', max_attempts=10, window=timedelta(hours=1))

# 한 IP 의 비밀번호 재설정 요청. 이것도 메일을 보낸다
PASSWORD_RESET_PER_IP = AttemptLimit(name='password-reset-ip', max_attempts=5, window=timedelta(hours=1))

# 한 사용자가 비밀번호 변경에서 현재 비밀번호를 틀린 횟수.
# 로그인한 뒤의 API 라서 IP 가 아니라 사용자로 센다.
# access 토큰을 훔친 사람이 현재 비밀번호를 맞혀 보는 것을 막는다
PASSWORD_CHANGE_FAILURES_PER_USER = AttemptLimit(
    name='password-change-fail-user', max_attempts=5, window=timedelta(minutes=15),
)


def check_login_attempt(*, ip: str, username: str) -> None:
    """
    이 IP 가 이 계정에 로그인을 시도해도 되는지 본다. 너무 많이 틀렸으면 TooManyAttemptsError 를 낸다.

    비밀번호를 확인하기 전에 부른다. 막힌 동안에는 맞는 비밀번호도 확인하지 않는다.
    확인해 주면 막힌 상태에서도 비밀번호를 계속 맞혀 볼 수 있다.
    """
    ensure_not_blocked(LOGIN_FAILURES_PER_ACCOUNT_AND_IP, _account_and_ip(username, ip))


def record_login_failure(*, ip: str, username: str) -> None:
    """
    아이디 또는 비밀번호가 틀렸음을 센다.

    없는 아이디여도 똑같이 센다. 있는 아이디만 세면, 막히는지 여부로 가입 여부가 드러난다.
    """
    count_failure(LOGIN_FAILURES_PER_ACCOUNT_AND_IP, _account_and_ip(username, ip))


def record_login_success(*, ip: str, username: str) -> None:
    """비밀번호가 맞았다. 이 IP 가 이 계정에서 틀린 횟수를 지운다. IP 의 시도 횟수는 지우지 않는다."""
    clear_attempts(LOGIN_FAILURES_PER_ACCOUNT_AND_IP, _account_and_ip(username, ip))


def check_password_change_attempt(*, user: User) -> None:
    """
    비밀번호 변경을 시도해도 되는지 본다. 현재 비밀번호를 너무 많이 틀렸으면 TooManyAttemptsError 를 낸다.

    현재 비밀번호를 확인하기 전에 부른다.
    """
    ensure_not_blocked(PASSWORD_CHANGE_FAILURES_PER_USER, _user(user))


def record_password_change_failure(*, user: User) -> None:
    count_failure(PASSWORD_CHANGE_FAILURES_PER_USER, _user(user))


def record_password_change_success(*, user: User) -> None:
    clear_attempts(PASSWORD_CHANGE_FAILURES_PER_USER, _user(user))


def _account_and_ip(username: str, ip: str) -> str:
    """
    (계정, IP) 쌍을 가리키는 문자열.

    아이디는 입력된 그대로가 아니라 공백을 떼고 소문자로 바꿔 쓴다.
    "Player" 와 "player " 를 따로 세면 표기를 바꿔 가며 횟수를 늘릴 수 있다.
    """
    return f'{username.strip().lower()}|{ip}'


def _user(user: User) -> str:
    return str(user.public_id)
