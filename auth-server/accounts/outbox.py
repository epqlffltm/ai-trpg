# auth-server/accounts/outbox.py

"""
메일 발송함. 보낼 메일을 적어 두는 일과, 적힌 메일을 꺼내 보내는 일.

적는 쪽(enqueue_mail)은 요청을 처리하는 중에 불린다. DB 에 한 줄을 쓰고 끝난다.
보내는 쪽(deliver_due_mail)은 워커가 부른다. 메일 서버와 통신하고, 실패하면 다시 시도한다.

적는 일이 계정 생성이나 코드 발급과 같은 트랜잭션에 들어간다. 그래서
"계정은 만들어졌는데 보낼 메일은 적히지 않은" 상태나 그 반대가 생기지 않는다.
"""

import logging
import smtplib
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from accounts.models import OutgoingMail, OutgoingMailStatus, SecurityEventKind
from accounts.security_events import record_security_event

logger = logging.getLogger(__name__)

# 이 시간 안에 보내지 못한 메일은 버린다. 인증 코드의 유효 시간(5분)과 같다
MAIL_SEND_DEADLINE = timedelta(minutes=5)

# 실패한 뒤 다시 시도하기까지의 간격. 실패할 때마다 두 배가 된다(5초, 10초, 20초, ...).
# 메일 서버가 죽어 있을 때 쉬지 않고 두드리지 않기 위해서다
FIRST_RETRY_DELAY = timedelta(seconds=5)

# 워커가 한 번에 처리하는 최대 개수
DEFAULT_BATCH_SIZE = 20


@dataclass(frozen=True)
class DeliveryReport:
    """워커가 한 번 돌면서 한 일."""

    sent: int = 0
    retried: int = 0
    discarded: int = 0

    @property
    def handled(self) -> int:
        return self.sent + self.retried + self.discarded


def enqueue_mail(*, to_email: str, subject: str, body: str) -> None:
    """
    메일을 보내 달라고 맡긴다.

    발송함에 적기만 하고 돌아온다. 실제 발송은 워커가 한다.
    MAIL_DELIVERY 가 'inline' 이면 발송함을 거치지 않고 그 자리에서 보낸다.
    inline 은 테스트와, 워커를 띄우지 않은 개발 환경을 위한 것이다.
    """
    if settings.MAIL_DELIVERY == 'inline':
        _send(to_email=to_email, subject=subject, body=body)
        return

    now = timezone.now()
    OutgoingMail.objects.create(
        to_email=to_email,
        subject=subject,
        body=body,
        next_attempt_at=now,
        expires_at=now + MAIL_SEND_DEADLINE,
    )


def deliver_due_mail(*, batch_size: int = DEFAULT_BATCH_SIZE) -> DeliveryReport:
    """지금 보낼 수 있는 메일을 최대 batch_size 개 처리하고, 한 일을 돌려준다."""
    counts = {'sent': 0, 'retried': 0, 'discarded': 0}
    for _ in range(batch_size):
        outcome = _deliver_next()
        if outcome is None:
            break
        counts[outcome] += 1
    return DeliveryReport(**counts)


def _deliver_next() -> str | None:
    """
    보낼 차례가 된 메일 하나를 처리한다. 처리할 메일이 없으면 None 을 돌려준다.

    메일 한 통이 트랜잭션 하나다. 행을 잠근 채로 보내고, 결과를 적고, 잠금을 푼다.
    보내는 도중 워커가 죽으면 트랜잭션이 취소되어 그 메일은 다시 대기 상태로 남는다.
    """
    now = timezone.now()

    with transaction.atomic():
        mail = _lock_next_due_mail(now)
        if mail is None:
            return None
        if now >= mail.expires_at:
            _discard(mail, now)
            return 'discarded'
        try:
            _send(to_email=mail.to_email, subject=mail.subject, body=mail.body)
        except (smtplib.SMTPException, OSError) as exc:
            # OSError 는 연결 실패와 시간 초과를 포함한다
            _schedule_retry(mail, exc, now)
            return 'retried'
        # 본문에 인증 코드가 들어 있다. 보낸 메일은 남기지 않는다
        mail.delete()
        return 'sent'


def _lock_next_due_mail(now) -> OutgoingMail | None:
    """
    보낼 차례가 된 메일 하나를 잠그고 가져온다.

    skip_locked 는 다른 워커가 잠근 행을 기다리지 않고 건너뛴다.
    워커를 여러 개 띄워도 같은 메일을 두 번 보내지 않고, 서로를 기다리지도 않는다.
    """
    return (
        OutgoingMail.objects
        .select_for_update(skip_locked=True)
        .filter(status=OutgoingMailStatus.PENDING, next_attempt_at__lte=now)
        .order_by('next_attempt_at', 'id')
        .first()
    )


def _send(*, to_email: str, subject: str, body: str) -> None:
    """메일 서버(또는 개발용 출력)로 메일 한 통을 보낸다. 실패하면 예외가 난다."""
    send_mail(subject=subject, message=body, from_email=None, recipient_list=[to_email])


def _schedule_retry(mail: OutgoingMail, error: Exception, now) -> None:
    """
    실패를 기록하고 다음 시도 시각을 정한다.

    간격은 실패할 때마다 두 배가 된다. 다만 버리는 시각을 넘겨 미루지 않는다.
    넘겨 미루면 버려야 할 메일이 그 뒤까지 대기 상태로 남는다.
    """
    mail.attempts += 1
    delay = FIRST_RETRY_DELAY * (2 ** (mail.attempts - 1))
    mail.next_attempt_at = min(now + delay, mail.expires_at)
    mail.last_error = _describe(error)
    mail.save(update_fields=['attempts', 'next_attempt_at', 'last_error'])


def _discard(mail: OutgoingMail, now) -> None:
    """
    보내지 못한 메일을 버린다. 받는 사람에게는 알릴 방법이 없다. 운영자가 알 수 있게 기록을 남긴다.

    행은 남기고 본문만 지운다. 본문의 인증 코드는 이미 쓸모가 없지만 남겨 둘 이유도 없다.
    """
    mail.status = OutgoingMailStatus.DISCARDED
    mail.body = ''
    mail.discarded_at = now
    mail.save(update_fields=['status', 'body', 'discarded_at'])
    # 운영자에게 가는 요약 메일에 실린다. 버리는 것과 같은 트랜잭션이라 둘 중 하나만 남는 일이 없다
    record_security_event(kind=SecurityEventKind.MAIL_DISCARDED)
    # 받는 사람의 주소는 로그에 적지 않는다. 관리자 화면에서 번호로 찾는다
    logger.error(
        '메일을 보내지 못하고 버렸다. id=%s 제목=%s 시도=%s 마지막 오류=%s',
        mail.pk, mail.subject, mail.attempts, mail.last_error or '(시도하지 못함)',
    )


def _describe(error: Exception) -> str:
    """오류를 한 줄로 적는다. 저장 칸의 길이에 맞춰 자른다."""
    text = f'{type(error).__name__}: {error}'
    return text[:OutgoingMail._meta.get_field('last_error').max_length]
