# auth-server/accounts/email_codes.py

"""
이메일 인증 코드의 발급과 검증.

코드는 PostgreSQL 에 둔다. 로그인마다 인증 코드가 필요한데, 로그인은 이미
PostgreSQL 없이는 동작하지 않는다. 코드를 다른 저장소에 두면 로그인이 의존하는 것이
하나 더 늘어난다. 양도 로그인 한 번에 코드 하나라서 별도 저장소가 필요한 부하가 아니다.

HTTP 를 모른다. 메일 발송도 여기서 하지 않는다(mail.py).
"""

import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from accounts.models import EmailCode, User

CODE_LENGTH = 6

# 메일이 늦게 도착하는 경우를 감안한 최소한의 시간
CODE_LIFETIME = timedelta(minutes=5)

# 코드 하나에 허용하는 오답 횟수.
# 6자리는 100만 가지뿐이라, 횟수를 제한하지 않으면 전부 넣어 볼 수 있다
MAX_FAILED_ATTEMPTS = 5

# 발급 제한. 남의 메일함에 코드를 쏟아붓는 것을 막는다
ISSUE_COOLDOWN = timedelta(minutes=1)
ISSUE_WINDOW = timedelta(hours=1)
MAX_ISSUES_PER_WINDOW = 5


class EmailCodeCooldownError(Exception):
    """직전 발급에서 시간이 충분히 지나지 않았다."""

    def __init__(self, retry_after: timedelta):
        super().__init__()
        self.retry_after = retry_after


class EmailCodeLimitError(Exception):
    """정해진 시간 안에 발급할 수 있는 횟수를 넘었다."""

    def __init__(self, retry_after: timedelta):
        super().__init__()
        self.retry_after = retry_after


class InvalidEmailCodeError(Exception):
    """
    코드가 틀렸거나, 만료됐거나, 이미 쓰였거나, 발급된 적이 없다.

    이유를 구분하지 않는다. 구분하면 "코드는 맞는데 만료됐다" 같은 정보를
    코드를 추측하는 쪽에 알려 주게 된다.
    """


def generate_code() -> str:
    """
    숫자로 된 인증 코드를 만든다.

    random 이 아니라 secrets 를 쓴다. random 은 앞의 값들을 알면
    다음 값을 예측할 수 있는 의사난수라서 인증에 쓰면 안 된다.
    """
    return f'{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}'


def hash_code(code: str, *, user: User, purpose: str) -> str:
    """
    코드를 서버의 비밀키와 섞어 해시한다.

    그냥 해시하면 안 된다. 6자리 코드는 100만 가지뿐이라, DB 가 유출되면
    전부 해시해 보는 것으로 바로 원문을 찾는다. SECRET_KEY 를 섞으면 DB 만으로는 풀 수 없다.

    회원과 용도도 함께 섞는다. 같은 코드라도 회원과 용도가 다르면 해시가 달라져,
    한 행의 해시를 다른 행에 옮겨 쓸 수 없다.
    """
    return salted_hmac(
        key_salt=f'accounts.email_code:{purpose}:{user.pk}',
        value=code,
        algorithm='sha256',
    ).hexdigest()


def issue_email_code(*, user: User, purpose: str) -> str:
    """
    새 인증 코드를 발급하고 원문을 돌려준다. 원문은 메일로 보낼 때만 쓴다.

    전에 발급한 코드는 덮어써서 못 쓰게 된다. 유효한 코드는 항상 하나뿐이다.
    발급 제한에 걸리면 EmailCodeCooldownError 나 EmailCodeLimitError 를 낸다.
    """
    code = generate_code()
    now = timezone.now()

    with transaction.atomic():
        record = _lock_record(user=user, purpose=purpose, now=now)
        _ensure_issue_allowed(record, now)
        _count_issue(record, now)
        record.code_hash = hash_code(code, user=user, purpose=purpose)
        record.expires_at = now + CODE_LIFETIME
        record.failed_attempts = 0
        record.last_issued_at = now
        record.save()

    return code


def consume_email_code(*, user: User, purpose: str, code: str) -> None:
    """
    인증 코드가 맞는지 확인하고, 맞으면 다시 쓸 수 없게 한다.

    틀리면 InvalidEmailCodeError 를 낸다. 틀린 횟수는 그 전에 반드시 저장된다.

    durable=True 는 이 블록이 다른 트랜잭션 안에서 실행되는 것을 금지한다.
    바깥에 트랜잭션이 있으면, 여기서 낸 예외가 바깥 트랜잭션까지 되돌려
    틀린 횟수가 저장되지 않는다. 그러면 횟수 제한 없이 코드를 추측할 수 있게 된다.
    """
    now = timezone.now()

    with transaction.atomic(durable=True):
        # 행을 잠가, 같은 코드로 동시에 들어온 요청 중 하나만 통과시킨다
        record = _lock_existing_record(user=user, purpose=purpose)
        matched = record is not None and _matches(record, code, now)
        if matched:
            _discard_code(record)
        elif record is not None:
            _record_failure(record)

    # 예외를 블록 밖에서 낸다. 블록 안에서 내면 틀린 횟수의 저장이 취소된다
    if not matched:
        raise InvalidEmailCodeError


def _lock_record(*, user: User, purpose: str, now) -> EmailCode:
    """
    회원과 용도에 해당하는 행을 잠그고 가져온다. 없으면 만든다.

    만든 직후의 행은 "한 번도 발급하지 않은" 상태다. 쓸 수 있는 코드가 없고,
    마지막 발급 시각을 충분히 과거로 두어 첫 발급이 쿨다운에 걸리지 않게 한다.
    """
    long_ago = now - ISSUE_WINDOW
    EmailCode.objects.get_or_create(
        user=user,
        purpose=purpose,
        defaults={
            'code_hash': '',
            'expires_at': long_ago,
            'last_issued_at': long_ago,
            'window_started_at': now,
            'issued_in_window': 0,
        },
    )
    return EmailCode.objects.select_for_update().get(user=user, purpose=purpose)


def _lock_existing_record(*, user: User, purpose: str) -> EmailCode | None:
    return (
        EmailCode.objects
        .select_for_update()
        .filter(user=user, purpose=purpose)
        .first()
    )


def _ensure_issue_allowed(record: EmailCode, now) -> None:
    """발급 제한을 확인한다. 걸리면 언제 다시 시도할 수 있는지와 함께 예외를 낸다."""
    cooldown_ends_at = record.last_issued_at + ISSUE_COOLDOWN
    if now < cooldown_ends_at:
        raise EmailCodeCooldownError(retry_after=cooldown_ends_at - now)

    window_ends_at = record.window_started_at + ISSUE_WINDOW
    if now < window_ends_at and record.issued_in_window >= MAX_ISSUES_PER_WINDOW:
        raise EmailCodeLimitError(retry_after=window_ends_at - now)


def _count_issue(record: EmailCode, now) -> None:
    """
    발급 횟수를 센다. 구간이 지났으면 새 구간을 시작한다.

    구간은 첫 발급 시각에 고정된다. 제한에 걸린 뒤의 요청이 구간을 연장하지 않는다.
    연장하면 계속 누르는 사용자가 스스로를 영영 잠그게 된다.
    """
    if now >= record.window_started_at + ISSUE_WINDOW:
        record.window_started_at = now
        record.issued_in_window = 0
    record.issued_in_window += 1


def _matches(record: EmailCode, code: str, now) -> bool:
    """쓸 수 있는 코드가 있고, 만료되지 않았고, 입력과 일치하는지 본다."""
    if not record.code_hash:
        return False
    if now >= record.expires_at:
        return False
    expected = record.code_hash
    actual = hash_code(code, user=record.user, purpose=record.purpose)
    # 일치하는 앞부분의 길이에 따라 비교 시간이 달라지지 않게 한다
    return constant_time_compare(expected, actual)


def _record_failure(record: EmailCode) -> None:
    """틀린 횟수를 올린다. 한도에 닿으면 정답 코드까지 폐기한다."""
    if not record.code_hash:
        # 쓸 수 있는 코드가 없는 상태다. 셀 것이 없다
        return
    record.failed_attempts += 1
    if record.failed_attempts >= MAX_FAILED_ATTEMPTS:
        record.code_hash = ''
    record.save(update_fields=['failed_attempts', 'code_hash'])


def _discard_code(record: EmailCode) -> None:
    """코드를 다시 쓸 수 없게 한다. 발급 이력은 남긴다."""
    record.code_hash = ''
    record.save(update_fields=['code_hash'])