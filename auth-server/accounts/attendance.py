# auth-server/accounts/attendance.py

"""
출석과 보물 상자(결제 서버에서 옮겨 왔다, 2026-11-08 결정). 규칙은 attendance_rules.py 다.

일이 둘로 나뉜다.
  - 받는 쪽(claim_attendance): 사용자가 "출석"을 누르면 불린다. 오늘의 줄을 적고 끝난다. 주기의 며칠째, 하루 양,
    상자를 여는 날이면 상자의 결과를 정해 함께 적는다. 결제 서버를 부르지 않는다
  - 맡기는 쪽(deliver_due_attendance): 워커(manage.py send_welcome_credits)가 부른다. 적힌 줄의 실버를 결제 서버에
    맡긴다. 실패하면 간격을 늘려 다시 맡긴다(환영 크레딧과 같다). 실버는 몇 초 뒤 지갑에 들어간다

같은 사용자의 출석은 계정의 줄을 잠가 차례로 처리한다.
자정 무렵에 두 요청이 함께 와도 뒤의 것이 앞의 것의 줄을 보고 센다.
같은 날 두 번은 두 겹으로 막는다. 줄의 유일 제약(사용자, 날짜)과 결제 서버의 지급의 이름이다.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts import attendance_rules as rules
from accounts.backoff import retry_delay
from accounts.badges import award_attendance
from accounts.billing_client import GRANTED, BillingUnavailableError, grant_attendance_silver
from accounts.identity_status import identity_status_of
from accounts.models import AttendanceClaim, User, WelcomeCreditStatus
from accounts.welcome_credit import (
    BILLING_UNAVAILABLE_ERROR_CODE,
    DEFAULT_BATCH_SIZE,
    FIRST_RETRY_DELAY,
    MAX_RETRY_DELAY,
    DeliveryReport,
)

logger = logging.getLogger(__name__)

# 한 묶음을 처리하는 일의 이름. 로그의 operation 칸에 들어간다(docs/observability.md)
DELIVER_OPERATION = 'attendance.deliver'


class AttendanceVerificationRequiredError(Exception):
    """본인인증을 하지 않아 출석 보상을 받을 수 없다."""


class AttendanceAlreadyClaimedError(Exception):
    """오늘 이미 받았다. 아무것도 바뀌지 않는다."""


@dataclass(frozen=True)
class ChestResult:
    """연 보물 상자. 표의 버전과 나온 결과다."""

    table: str
    outcome: rules.Outcome


@dataclass(frozen=True)
class Claim:
    """받은 출석 보상."""

    day: date
    cycle_day: int
    silver: int
    # 연 날이 아니면 None 이다
    chest: ChestResult | None


@dataclass(frozen=True)
class Status:
    """오늘의 출석. 화면이 단추를 그릴 때 쓴다."""

    today: date
    # 본인인증을 했는지. False 면 받을 수 없다. 화면은 본인인증으로 보낸다
    verified: bool
    # 오늘 이미 받았는지
    claimed: bool
    # 받았으면 받은 날의 값, 아직이면 지금 받으면 될 값이다
    cycle_day: int
    # 오늘의 하루 양. 받았으면 받은 양이다
    silver: int
    # 오늘 보물 상자를 여는 날인지
    chest: bool


def schedule() -> tuple[int, ...]:
    """지금의 하루 양의 목록(설정 ATTENDANCE_SILVER). 서버가 뜰 때 이미 검사했다."""
    return settings.ATTENDANCE_SILVER


def _last_claim(user: User) -> rules.LastClaim | None:
    """그 사용자의 가장 최근 출석. 없으면 None."""
    row = AttendanceClaim.objects.filter(user=user).order_by('-day').values('day', 'cycle_day').first()
    return rules.LastClaim(day=row['day'], cycle_day=row['cycle_day']) if row else None


def attendance_status(user: User, now: datetime | None = None) -> Status:
    """그 사용자의 오늘 출석. 본인인증을 하지 않았어도 오류가 아니다(verified 가 False 다)."""
    now = now or timezone.now()
    today = rules.korean_date(now)
    verified = identity_status_of(user, today).verified
    claimed = AttendanceClaim.objects.filter(user=user, day=today).first()
    if claimed is not None:
        # 적어 둔 줄의 값을 그대로 보인다(그 사이 설정이 바뀌었어도)
        return Status(
            today=today,
            verified=verified,
            claimed=True,
            cycle_day=claimed.cycle_day,
            silver=claimed.silver,
            chest=claimed.chest_table is not None,
        )
    current = schedule()
    day = rules.cycle_day_on(_last_claim(user), today, len(current))
    return Status(
        today=today,
        verified=verified,
        claimed=False,
        cycle_day=day,
        silver=rules.silver_on(current, day),
        chest=rules.opens_chest(current, day),
    )


def _open_chest(cycle_day: int, roll: rules.Roll) -> ChestResult | None:
    """상자를 여는 날이면 연다. 아니면 None."""
    if not rules.opens_chest(schedule(), cycle_day):
        return None
    table = rules.CURRENT_CHEST
    return ChestResult(table=table.version, outcome=rules.pick(table, roll()))


def _decide(user: User, today: date, roll: rules.Roll) -> Claim:
    """오늘 받을 것을 정한다. 이미 받았으면 AttendanceAlreadyClaimedError. 계정의 줄을 잠근 트랜잭션 안이다."""
    last = _last_claim(user)
    if last is not None and last.day >= today:
        raise AttendanceAlreadyClaimedError
    current = schedule()
    cycle_day = rules.cycle_day_on(last, today, len(current))
    return Claim(
        day=today,
        cycle_day=cycle_day,
        silver=rules.silver_on(current, cycle_day),
        chest=_open_chest(cycle_day, roll),
    )


def _record(user: User, claim: Claim, now: datetime) -> None:
    """
    출석의 줄을 적는다.

    같은 날의 줄이 이미 있으면 AttendanceAlreadyClaimedError 다(잠금을 지나친 경우를 유일 제약이 막는다).
    """
    chest = claim.chest
    try:
        with transaction.atomic():
            AttendanceClaim.objects.create(
                user=user,
                day=claim.day,
                cycle_day=claim.cycle_day,
                silver=claim.silver,
                chest_table=chest.table if chest else None,
                chest_outcome=chest.outcome.id if chest else None,
                chest_silver=chest.outcome.silver if chest else 0,
                next_attempt_at=now,
            )
    except IntegrityError as exc:
        raise AttendanceAlreadyClaimedError from exc


def claim_attendance(user: User, now: datetime | None = None, roll: rules.Roll = rules.crypto_roll) -> Claim:
    """
    오늘의 출석 보상을 정하고 적는다. 실버는 워커가 결제 서버에 맡긴다(deliver_due_attendance).

    본인인증 전이면 AttendanceVerificationRequiredError, 오늘 이미 받았으면 AttendanceAlreadyClaimedError 다.
    """
    now = now or timezone.now()
    today = rules.korean_date(now)
    if not identity_status_of(user, today).verified:
        raise AttendanceVerificationRequiredError
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        claim = _decide(locked, today, roll)
        _record(locked, claim, now)
        # 출석으로 받는 활동 배지(#193). 같은 트랜잭션이다
        award_attendance(
            locked,
            opened_chest=claim.chest is not None,
            chest_outcome=claim.chest.outcome.id if claim.chest else None,
            now=now,
        )
    return claim


# --- 맡기기(워커) ---


def deliver_due_attendance(*, batch_size: int = DEFAULT_BATCH_SIZE) -> DeliveryReport:
    """지금 맡길 수 있는 줄을 최대 batch_size 개 처리하고, 한 일을 돌려준다."""
    counts = {'granted': 0, 'skipped': 0, 'retried': 0}
    for _ in range(batch_size):
        outcome = _deliver_next()
        if outcome is None:
            break
        counts[outcome] += 1
    return DeliveryReport(**counts)


def _deliver_next() -> str | None:
    """맡길 차례가 된 줄 하나를 처리한다. 처리할 줄이 없으면 None 이다. 줄 하나가 트랜잭션 하나다."""
    now = timezone.now()
    with transaction.atomic():
        row = _lock_next_due(now)
        if row is None:
            return None
        try:
            outcome = grant_attendance_silver(
                user_public_id=row.user.public_id, day=row.day, silver=row.silver, chest_silver=row.chest_silver
            )
        except BillingUnavailableError as exc:
            _schedule_retry(row, exc, now)
            return 'retried'
        _finish(row, outcome, now)
        return 'granted' if outcome == GRANTED else 'skipped'


def _lock_next_due(now: datetime) -> AttendanceClaim | None:
    """맡길 차례가 된 줄 하나를 잠그고 가져온다. 다른 워커가 잠근 줄은 건너뛴다."""
    return (
        AttendanceClaim.objects.select_for_update(skip_locked=True, of=('self',))
        .select_related('user')
        .filter(status=WelcomeCreditStatus.PENDING, next_attempt_at__lte=now)
        .order_by('next_attempt_at', 'id')
        .first()
    )


def _finish(row: AttendanceClaim, outcome: str, now: datetime) -> None:
    """맡길 일이 끝났다고 적는다. outcome 은 결제 서버가 돌려준 결과이고, 그대로 상태가 된다."""
    row.status = outcome
    row.finished_at = now
    row.last_error = ''
    row.save(update_fields=['status', 'finished_at', 'last_error'])


def _schedule_retry(row: AttendanceClaim, error: Exception, now: datetime) -> None:
    """실패를 기록하고 다음 시도 시각을 정한다. 간격은 두 배씩 늘고 MAX_RETRY_DELAY 에서 멈춘다. 버리지 않는다."""
    row.attempts += 1
    row.next_attempt_at = now + retry_delay(row.attempts, first=FIRST_RETRY_DELAY, maximum=MAX_RETRY_DELAY)
    row.last_error = str(error)[: AttendanceClaim._meta.get_field('last_error').max_length]
    row.save(update_fields=['attempts', 'next_attempt_at', 'last_error'])
    # 받는 사람은 적지 않는다. 관리자 화면에서 번호로 찾는다
    logger.warning(
        '출석의 실버를 결제 서버에 맡기지 못했다. 나중에 다시 시도한다',
        extra={
            'operation': DELIVER_OPERATION,
            'error_code': BILLING_UNAVAILABLE_ERROR_CODE,
            'error_message': row.last_error,
            'attendance_claim_id': row.pk,
            'attempt': row.attempts,
        },
    )
