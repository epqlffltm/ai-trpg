# auth-server/accounts/outbox.py

"""
메일 발송함. 보낼 메일을 적어 두는 일과, 적힌 메일을 꺼내 보내는 일.

적는 쪽(enqueue_mail)은 요청을 처리하는 중에 불린다. DB 에 한 줄을 쓰고 끝난다.
보내는 쪽(deliver_due_mail)은 워커가 부른다. 메일 서버와 통신하고, 실패하면 다시 시도한다.
메일 서버와 통신하는 동안에는 트랜잭션도 행 잠금도 쥐지 않는다(#24). 차지하기, 보내기, 마무리 세 걸음이다.

본문은 암호화해서 적는다(mail_crypto.py). 워커가 꺼낼 때 복호화한다.

보낸 메일의 줄은 지운다. 보냈다는 사실을 남겨야 하는 메일은 기록(MailReceipt)을 붙여 적는다(#352).
보내면 그 기록에 보낸 시각을, 버리면 버린 시각을 적는다.

적는 일이 계정 생성이나 코드 발급과 같은 트랜잭션에 들어간다. 그래서
"계정은 만들어졌는데 보낼 메일은 적히지 않은" 상태나 그 반대가 생기지 않는다.
"""

import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from accounts.mail_crypto import UnreadableMailBodyError, decrypt_mail_body, encrypt_mail_body
from accounts.models import MailReceipt, OutgoingMail, OutgoingMailStatus, SecurityEventKind
from accounts.security_events import record_security_event

logger = logging.getLogger(__name__)

# 이 시간 안에 보내지 못한 메일은 버린다. 인증 코드의 유효 시간(5분)과 같다
MAIL_SEND_DEADLINE = timedelta(minutes=5)

# 실패한 뒤 다시 시도하기까지의 간격. 실패할 때마다 두 배가 된다(5초, 10초, 20초, ...).
# 메일 서버가 죽어 있을 때 쉬지 않고 두드리지 않기 위해서다
FIRST_RETRY_DELAY = timedelta(seconds=5)

# 워커가 한 번에 처리하는 최대 개수
DEFAULT_BATCH_SIZE = 20

# 워커가 메일 하나를 차지하고 보내는 데 쓸 수 있는 시간. 지나면 다른 워커가 다시 가져간다.
# 메일 서버의 시간 제한(SMTP_TIMEOUT, 10초)은 연결, 인사, 암호화, 인증, 보내기의 단계마다 따로 걸린다.
# 그 여러 단계보다 넉넉하고, 버리는 시각(5분) 안에 한 번 더 차지할 여유가 남는 길이다
MAIL_CLAIM_LEASE = timedelta(minutes=2)

# 임대가 끝난 메일을 다시 가져갈 때 마지막 오류 칸에 적는 글
LEASE_EXPIRED_ERROR = '이전 시도가 정한 시간 안에 끝나지 않았다(워커가 멈췄거나 죽었다)'


@dataclass(frozen=True)
class DeliveryReport:
    """워커가 한 번 돌면서 한 일."""

    sent: int = 0
    retried: int = 0
    discarded: int = 0

    @property
    def handled(self) -> int:
        return self.sent + self.retried + self.discarded


@dataclass(frozen=True)
class ClaimedMail:
    """
    워커가 차지한 메일 한 통. 트랜잭션 밖에서 보낼 때 쓰는 값을 담는다.

    attempt 는 차지할 때 올린 시도 횟수다. 마무리할 때 이 값이 그대로인지 보고 고친다.
    그 사이에 임대가 끝나 다른 워커가 다시 가져갔다면 횟수가 달라져 있다. 남의 차지를 지우거나 덮지 않는다.
    """

    pk: int
    attempt: int
    expires_at: datetime
    to_email: str
    subject: str
    body: str
    # 보냈다는 것을 남길 기록. 없으면 None 이다
    receipt_id: int | None = None


def enqueue_mail(
    *,
    to_email: str,
    subject: str,
    body: str,
    receipt: MailReceipt | None = None,
    deadline: timedelta = MAIL_SEND_DEADLINE,
) -> None:
    """
    메일을 보내 달라고 맡긴다.

    발송함에 적기만 하고 돌아온다. 실제 발송은 워커가 한다.
    MAIL_DELIVERY 가 'inline' 이면 발송함을 거치지 않고 그 자리에서 보낸다.
    inline 은 테스트와, 워커를 띄우지 않은 개발 환경을 위한 것이다.

    receipt 를 주면 보냈거나 버렸을 때 그 기록에 적는다. deadline 은 버리기까지의 시간이다.
    인증 코드는 5분이 지나면 쓸모가 없지만, 결제 알림은 하루 늦어도 쓸모가 있다.
    """
    if settings.MAIL_DELIVERY == 'inline':
        _send(to_email=to_email, subject=subject, body=body)
        _mark_receipt(receipt.pk if receipt else None, sent_at=timezone.now())
        return

    now = timezone.now()
    OutgoingMail.objects.create(
        to_email=to_email,
        subject=subject,
        # 본문에는 인증 코드나 재설정 토큰이 들어 있다. 암호화해서 적는다
        body=encrypt_mail_body(body),
        next_attempt_at=now,
        expires_at=now + deadline,
        receipt=receipt,
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

    차지하기와 마무리는 각각 짧은 트랜잭션이다. 메일 서버와 통신하는 동안에는 DB 의 연결도 잠금도 쥐지 않는다.
    보내는 도중 워커가 죽으면 임대(MAIL_CLAIM_LEASE)가 끝난 뒤 다른 워커가 다시 가져간다.
    """
    claimed = _claim_next_due_mail(timezone.now())
    if claimed is None or claimed == 'discarded':
        return claimed
    try:
        _send(to_email=claimed.to_email, subject=claimed.subject, body=claimed.body)
    except (smtplib.SMTPException, OSError) as exc:
        # OSError 는 연결 실패와 시간 초과를 포함한다
        _schedule_retry(claimed, exc, timezone.now())
        return 'retried'
    _finish_sent(claimed)
    return 'sent'


def _claim_next_due_mail(now) -> ClaimedMail | str | None:
    """
    보낼 차례가 된 메일 하나를 차지한다. 짧은 트랜잭션 하나다.

    버릴 메일이면 그 자리에서 버리고 'discarded' 를, 보낼 메일이 없으면 None 을 돌려준다.
    차지하면 상태를 '보내는 중' 으로, 다음 시도 시각을 임대가 끝나는 시각으로 바꾸고 커밋한다.
    """
    with transaction.atomic():
        mail = _lock_next_due_mail(now)
        if mail is None:
            return None
        if mail.status == OutgoingMailStatus.SENDING:
            _note_expired_lease(mail)
        if now >= mail.expires_at:
            _discard(mail, now)
            return 'discarded'
        try:
            body = decrypt_mail_body(mail.body)
        except UnreadableMailBodyError as exc:
            # 다시 시도해도 읽을 수 없다. 바로 버린다
            mail.last_error = _describe(exc)
            _discard(mail, now)
            return 'discarded'
        _mark_sending(mail, now)
    return ClaimedMail(
        pk=mail.pk,
        attempt=mail.attempts,
        expires_at=mail.expires_at,
        to_email=mail.to_email,
        subject=mail.subject,
        body=body,
        receipt_id=mail.receipt_id,
    )


def _lock_next_due_mail(now) -> OutgoingMail | None:
    """
    보낼 차례가 된 메일 하나를 잠그고 가져온다.

    skip_locked 는 다른 워커가 차지하는 중(잠금은 짧다)인 행을 기다리지 않고 건너뛴다.
    대기 중인 메일과, 임대가 끝난 '보내는 중' 메일을 함께 고른다.
    보내는 중인 메일의 다음 시도 시각은 임대가 끝나는 시각이다.
    """
    return (
        OutgoingMail.objects.select_for_update(skip_locked=True)
        .filter(status__in=[OutgoingMailStatus.PENDING, OutgoingMailStatus.SENDING], next_attempt_at__lte=now)
        .order_by('next_attempt_at', 'id')
        .first()
    )


def _send(*, to_email: str, subject: str, body: str) -> None:
    """메일 서버(또는 개발용 출력)로 메일 한 통을 보낸다. 실패하면 예외가 난다."""
    send_mail(subject=subject, message=body, from_email=None, recipient_list=[to_email])


def _mark_sending(mail: OutgoingMail, now) -> None:
    """
    메일을 차지했다고 적는다. 시도 횟수를 올리고, 다음 시도 시각을 임대가 끝나는 시각으로 둔다.

    시도 횟수는 실패한 횟수가 아니라 시작한 횟수다. 마무리할 때 남의 차지인지 가리는 값으로도 쓴다.
    """
    mail.status = OutgoingMailStatus.SENDING
    mail.attempts += 1
    mail.next_attempt_at = now + MAIL_CLAIM_LEASE
    mail.save(update_fields=['status', 'attempts', 'next_attempt_at', 'last_error'])


def _note_expired_lease(mail: OutgoingMail) -> None:
    """
    임대가 끝난 메일을 다시 가져간다고 남긴다. 앞의 워커가 보냈는지 모르므로 이 메일은 두 번 갈 수 있다.

    받는 사람의 주소는 로그에 적지 않는다.
    """
    mail.last_error = LEASE_EXPIRED_ERROR
    logger.warning('임대가 끝난 메일을 다시 가져간다. id=%s 시도=%s', mail.pk, mail.attempts)


def _owned(claimed: ClaimedMail):
    """이 워커가 차지한 그대로인 행만 고르는 조건. 다른 워커가 다시 가져갔으면 아무것도 고르지 않는다."""
    return OutgoingMail.objects.filter(pk=claimed.pk, status=OutgoingMailStatus.SENDING, attempts=claimed.attempt)


def _finish_sent(claimed: ClaimedMail) -> None:
    """
    보낸 메일의 행을 지운다. 본문에 인증 코드가 들어 있어 남기지 않는다.

    지울 행이 없으면 임대가 끝나 다른 워커가 다시 가져간 것이다. 메일이 두 번 갔을 수 있다.
    """
    deleted, _ = _owned(claimed).delete()
    if deleted == 0:
        logger.warning('보낸 메일을 다른 워커가 이미 다시 가져갔다. 두 번 갔을 수 있다. id=%s', claimed.pk)
    # 보낸 것은 사실이다. 다른 워커가 다시 가져갔어도 기록에는 먼저 보낸 시각이 남는다
    _mark_receipt(claimed.receipt_id, sent_at=timezone.now())


def _schedule_retry(claimed: ClaimedMail, error: Exception, now) -> None:
    """
    실패를 기록하고 대기 상태로 돌려 다음 시도 시각을 정한다.

    간격은 실패할 때마다 두 배가 된다. 다만 버리는 시각을 넘겨 미루지 않는다.
    넘겨 미루면 버려야 할 메일이 그 뒤까지 대기 상태로 남는다.
    """
    delay = FIRST_RETRY_DELAY * (2 ** (claimed.attempt - 1))
    updated = _owned(claimed).update(
        status=OutgoingMailStatus.PENDING,
        next_attempt_at=min(now + delay, claimed.expires_at),
        last_error=_describe(error),
    )
    if updated == 0:
        logger.warning('실패를 적으려던 메일을 다른 워커가 이미 다시 가져갔다. id=%s', claimed.pk)


def _discard(mail: OutgoingMail, now) -> None:
    """
    보내지 못한 메일을 버린다. 받는 사람에게는 알릴 방법이 없다. 운영자가 알 수 있게 기록을 남긴다.

    행은 남기고 본문만 지운다. 본문의 인증 코드는 이미 쓸모가 없지만 남겨 둘 이유도 없다.
    """
    mail.status = OutgoingMailStatus.DISCARDED
    mail.body = ''
    mail.discarded_at = now
    mail.save(update_fields=['status', 'body', 'discarded_at', 'last_error'])
    _mark_receipt(mail.receipt_id, discarded_at=now)
    # 운영자에게 가는 요약 메일에 실린다. 버리는 것과 같은 트랜잭션이라 둘 중 하나만 남는 일이 없다
    record_security_event(kind=SecurityEventKind.MAIL_DISCARDED)
    # 받는 사람의 주소는 로그에 적지 않는다. 관리자 화면에서 번호로 찾는다
    logger.error(
        '메일을 보내지 못하고 버렸다. id=%s 제목=%s 시도=%s 마지막 오류=%s',
        mail.pk,
        mail.subject,
        mail.attempts,
        mail.last_error or '(시도하지 못함)',
    )


def _mark_receipt(receipt_id: int | None, **when) -> None:
    """
    보낸 메일의 기록에 보낸 시각(sent_at)이나 버린 시각(discarded_at)을 적는다. 기록이 없으면 아무것도 하지 않는다.

    이미 적힌 시각은 덮지 않는다. 처음 보낸 때가 남는다.
    """
    if receipt_id is None:
        return
    (field,) = when
    MailReceipt.objects.filter(pk=receipt_id, **{f'{field}__isnull': True}).update(**when)


def _describe(error: Exception) -> str:
    """오류를 한 줄로 적는다. 저장 칸의 길이에 맞춰 자른다."""
    text = f'{type(error).__name__}: {error}'
    return text[: OutgoingMail._meta.get_field('last_error').max_length]
