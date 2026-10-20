# trpg-server/app/notifications/dispatcher.py

"""
발송함의 알림을 알림 서버에 보내는 작업. 몇 초마다 한 바퀴 돈다.

한 바퀴에 두 가지를 한다.
  1. 오래(STALE_AFTER, 7일) 보내지 못한 알림을 지운다. 알림 서버가 오래 죽어 있었거나 주소를 비워 둔 동안 쌓인 것이다.
     그만큼 지난 알림(은퇴 7 일 전 같은 것)은 이미 쓸모가 없고, 쌓아 두면 알림 서버가 돌아올 때 한꺼번에 몰린다
  2. 보낼 차례가 된 알림(DISPATCH_BATCH, 50 개까지)을 하나씩 보내고 결과를 적는다
     - 보냈다: 줄을 지운다
     - 다시 보낼 일: 기다리는 시간을 늘려 다시 보낸다(retry_delay, 10초에서 두 배씩 1시간까지)
     - 받지 않았다: 실패로 적고 다시 보내지 않는다. 버그라 오류로 남긴다

알림 서버를 부르는 것(notifications)이 없으면(NOTIFICATION_URL 을 비웠다) 1 만 한다. 알림은 적히기만 한다.

서버가 여럿이면 모두 같은 일을 한다. 같은 알림을 둘이 보내도 알림 서버는 열쇠(source_key)로 한 줄만 둔다.
결과는 "아직 기다리는 줄일 때만" 적는다(app/notifications/repository.py).

로그는 청구 정리와 같은 규칙이다(app/billing/settler.py). 바퀴마다 job_id 를 걸고, operation 은 notification.send 다.
받는 사람과 알림의 내용은 남기지 않는다. 알림의 종류(kind)와 발송함의 번호만 남긴다.
지운 수와 찾아낸 알림의 수를 바퀴의 span 에 싣는다(add_handled). 둘 다 없던 바퀴의 추적은 보내지 않는다.
바퀴마다 작업의 메트릭(background_jobs_*)을 센다(app/observability/metrics.py 의 measured_job).
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import loops
from app.core.jobs import JOB_FAILED_ERROR_CODE, elapsed_ms
from app.core.loops import Running
from app.notifications import repository
from app.notifications.client import Delivery, Notifications, Sent
from app.notifications.models import OutgoingNotification
from app.observability.context import job_scope
from app.observability.identifiers import new_job_id
from app.observability.metrics import measured_job
from app.observability.spans import add_handled, job_span

logger = logging.getLogger(__name__)

# 몇 초마다 보는가
DISPATCH_INTERVAL_SECONDS = 5.0
# 한 바퀴에 보내는 알림의 수. 밀리면 다음 바퀴에 마저 보낸다
DISPATCH_BATCH = 50
# 이보다 오래 보내지 못한 알림은 보내지 않고 지운다
STALE_AFTER = timedelta(days=7)
# 다시 보내기까지 기다리는 시간. 처음 10초, 한 번 더 못 보낼 때마다 두 배, 1시간까지
RETRY_BASE_SECONDS = 10
RETRY_MAX_SECONDS = 60 * 60
# 로그의 operation 과 error_code. 정해진 이름이다(docs/observability.md)
DISPATCH_OPERATION = 'notification.send'
UNAVAILABLE_ERROR_CODE = 'notification.unavailable'
REJECTED_ERROR_CODE = 'notification.rejected'


def now_utc() -> datetime:
    """지금 시각(UTC)."""
    return datetime.now(UTC)


def retry_delay(attempts: int) -> timedelta:
    """attempts 번째로 보내지 못한 뒤에 다시 보내기까지 기다리는 시간."""
    seconds = RETRY_BASE_SECONDS * 2 ** max(attempts - 1, 0)
    return timedelta(seconds=min(seconds, RETRY_MAX_SECONDS))


@dataclass(frozen=True)
class Dispatched:
    """한 바퀴에 한 일. 보낸 수, 다시 보낼 수, 받지 않은 수, 보내다 예외가 난 수, 오래되어 지운 수."""

    sent: int = 0
    retried: int = 0
    rejected: int = 0
    failed: int = 0
    dropped: int = 0

    def busy(self) -> bool:
        """한 일이 있었는가."""
        return bool(self.sent or self.retried or self.rejected or self.failed or self.dropped)


def add(dispatched: Dispatched, delivery: Delivery | None) -> Dispatched:
    """알림 하나를 보낸 것을 더한다. None 이면 보내다 예외가 났다."""
    return Dispatched(
        sent=dispatched.sent + (delivery == Delivery.DELIVERED),
        retried=dispatched.retried + (delivery == Delivery.UNAVAILABLE),
        rejected=dispatched.rejected + (delivery == Delivery.REJECTED),
        failed=dispatched.failed + (delivery is None),
        dropped=dispatched.dropped,
    )


async def record(session: AsyncSession, notification: OutgoingNotification, sent: Sent, now: datetime) -> None:
    """보낸 결과를 발송함에 적는다. 저장하지 않는다."""
    if sent.delivery == Delivery.DELIVERED:
        await repository.remove(session, notification.id)
    elif sent.delivery == Delivery.UNAVAILABLE:
        next_attempt_at = now + retry_delay(notification.attempts + 1)
        await repository.postpone(session, notification.id, next_attempt_at, sent.reason or '')
    else:
        await repository.mark_failed(session, notification.id, sent.reason or '')


def log_unsent(notification: OutgoingNotification, sent: Sent) -> None:
    """
    보내지 못한 알림을 로그에 남긴다. 보냈으면 남기지 않는다(바퀴의 줄에 수가 있다).

    다시 보낼 일은 warning 이다. 서명이 거절된 것(401)은 설정을 고쳐야 낫는 일이라 error 다.
    받지 않은 것은 버그라 error 다.
    """
    if sent.delivery == Delivery.DELIVERED:
        return
    rejected = sent.delivery == Delivery.REJECTED
    level = logging.ERROR if rejected or sent.reason == 'unauthorized' else logging.WARNING
    logger.log(
        level,
        '알림 서버가 알림을 받지 않았습니다' if rejected else '알림을 보내지 못했습니다. 다시 보냅니다',
        extra={
            'operation': DISPATCH_OPERATION,
            'notification_id': notification.id,
            'kind': notification.kind,
            'result': 'client_error' if rejected else 'server_error',
            'error_code': REJECTED_ERROR_CODE if rejected else UNAVAILABLE_ERROR_CODE,
            'reason': sent.reason,
        },
    )


@dataclass(frozen=True)
class NotificationDispatcher:
    """
    발송함의 알림을 보내는 작업.

    notifications 는 부를 때마다 앱에서 꺼낸다. 테스트가 알림 서버를 바꿔 꽂으면 그 뒤부터 바뀐 것을 쓴다.
    None 이면 보내지 않는다(NOTIFICATION_URL 을 비웠다). clock 은 테스트가 바꿔 꽂는다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    notifications: Callable[[], Notifications | None]
    interval: float = DISPATCH_INTERVAL_SECONDS
    clock: Callable[[], datetime] = now_utc

    async def drop_stale(self, now: datetime) -> int:
        """오래 보내지 못한 알림을 지운다. 지운 수."""
        async with self.session_factory() as session:
            dropped = await repository.drop_stale(session, now - STALE_AFTER)
            await session.commit()
            return dropped

    async def due(self, now: datetime) -> list[OutgoingNotification]:
        """보낼 차례가 된 알림들. 잠그지 않는다."""
        async with self.session_factory() as session:
            return await repository.find_due(session, now, DISPATCH_BATCH)

    async def deliver(self, notifications: Notifications, notification: OutgoingNotification, now: datetime) -> Sent:
        """알림 하나를 보내고 결과를 제 세션에 적는다. 알림 서버를 부르는 동안 DB 의 연결을 쥐지 않는다."""
        sent = await notifications.send(notification)
        async with self.session_factory() as session:
            await record(session, notification, sent, now)
            await session.commit()
        log_unsent(notification, sent)
        return sent

    async def deliver_safely(
        self, notifications: Notifications, notification: OutgoingNotification, now: datetime
    ) -> Delivery | None:
        """알림 하나를 보낸다. 예외가 나면 로그에 남기고 None. 한 알림이 실패해도 다른 알림은 보낸다."""
        try:
            return (await self.deliver(notifications, notification, now)).delivery
        except Exception:
            logger.exception(
                '알림을 보내지 못했습니다',
                extra={
                    'operation': DISPATCH_OPERATION,
                    'notification_id': notification.id,
                    'kind': notification.kind,
                    'result': 'server_error',
                    'error_code': JOB_FAILED_ERROR_CODE,
                },
            )
            return None

    async def sweep(self) -> Dispatched:
        """한 바퀴의 일. 오래된 알림을 지우고, 보낼 곳이 있으면 차례가 된 알림을 보낸다."""
        now = self.clock()
        dispatched = Dispatched(dropped=await self.drop_stale(now))
        add_handled(dispatched.dropped)
        notifications = self.notifications()
        if notifications is None:
            return dispatched
        due = await self.due(now)
        add_handled(len(due))
        for notification in due:
            dispatched = add(dispatched, await self.deliver_safely(notifications, notification, now))
        return dispatched

    async def tick(self) -> Dispatched:
        """
        한 바퀴. 제 job_id 를 걸고 보낸 뒤, 어떻게 끝났는지 한 줄을 남긴다.

        찾는 일이 통째로 실패하면(DB 가 없다) 예외를 그대로 올린다. 그 줄은 도는 쪽(run)이 남긴다.
        """
        job_id = new_job_id()
        with job_span(DISPATCH_OPERATION, job_id), job_scope(job_id), measured_job(DISPATCH_OPERATION):
            started = time.perf_counter()
            dispatched = await self.sweep()
            logger.log(
                logging.INFO if dispatched.busy() else logging.DEBUG,
                '알림 보내기가 한 바퀴를 돌았습니다',
                extra={
                    'operation': DISPATCH_OPERATION,
                    'sent': dispatched.sent,
                    'retried': dispatched.retried,
                    'rejected': dispatched.rejected,
                    'failed': dispatched.failed,
                    'dropped': dispatched.dropped,
                    'duration_ms': elapsed_ms(started),
                    'result': 'success',
                },
            )
            return dispatched

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 interval 마다 한 바퀴씩 돈다. 한 바퀴가 통째로 실패해도 멈추지 않는다."""
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception(
                    '알림 보내기가 한 바퀴를 돌지 못했습니다',
                    extra={
                        'operation': DISPATCH_OPERATION,
                        'result': 'server_error',
                        'error_code': JOB_FAILED_ERROR_CODE,
                    },
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def start(dispatcher: NotificationDispatcher) -> Running:
    """알림 보내기를 돌리기 시작한다. 서버가 뜰 때 부른다."""
    return loops.start(dispatcher, 'notification-dispatcher')
