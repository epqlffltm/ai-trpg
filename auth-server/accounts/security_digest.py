# auth-server/accounts/security_digest.py

"""
보안 이벤트를 운영자에게 알리고, 오래된 기록을 지운다.

사건마다 메일을 보내지 않고 모아서 보낸다. 공격은 사건을 한꺼번에 많이 만든다.
사건마다 보내면 운영자의 메일함이 넘치고, 정작 읽지 않게 된다.

주기적으로 부른다(manage.py send_security_digest). 부를 때마다
"아직 알리지 않은 사건" 을 전부 모아 한 통으로 보낸다. 없으면 보내지 않는다.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.mail import send_security_digest
from accounts.models import SecurityEvent

# 보안 이벤트를 보관하는 기간. 지나면 지운다.
# IP 주소와 "어느 계정이 공격받았는가" 가 들어 있다. 필요한 기간을 넘겨 쌓아 두지 않는다
EVENT_RETENTION = timedelta(days=30)

# 요약 한 통에 싣는 사건의 최대 수. 남은 사건은 다음 실행에서 알린다.
# 한도 없이 전부 읽으면, 사건이 한꺼번에 많이 쌓였을 때 그 전부를 메모리에 올리고
# 그 전부를 잠근 채로 트랜잭션을 오래 쥔다. 공격자가 사건을 많이 만들수록 요약이 무거워진다
MAX_EVENTS_PER_DIGEST = 1000


def report_new_security_events() -> int:
    """
    아직 알리지 않은 보안 이벤트를 모아 운영자에게 메일로 보내고, 알린 건수를 돌려준다.

    한 번에 MAX_EVENTS_PER_DIGEST 건까지, 오래된 것부터 알린다. 남은 것은 다음 실행에서 알린다.

    받는 사람(SECURITY_DIGEST_TO)이 없으면 아무것도 하지 않는다. 사건은 알리지 않은 채로 남는다.

    메일을 발송함에 적는 것과 "알렸다" 고 표시하는 것이 한 트랜잭션이다.
    둘 중 하나만 되는 일이 없다. 그래서 같은 사건을 두 번 알리거나 빠뜨리지 않는다.
    """
    recipients = settings.SECURITY_DIGEST_TO
    if not recipients:
        return 0

    with transaction.atomic():
        events = _lock_unreported_events()
        if not events:
            return 0
        send_security_digest(recipients=recipients, events=events)
        _mark_reported(events)
    return len(events)


def delete_old_security_events() -> int:
    """보관 기간이 지난 보안 이벤트를 지우고, 지운 건수를 돌려준다."""
    cutoff = timezone.now() - EVENT_RETENTION
    deleted, _ = SecurityEvent.objects.filter(created_at__lt=cutoff).delete()
    return deleted


def _lock_unreported_events() -> list[SecurityEvent]:
    """
    아직 알리지 않은 사건을 오래된 것부터 MAX_EVENTS_PER_DIGEST 건까지 잠그고 가져온다.

    잠그는 이유: 요약이 동시에 두 번 돌면 둘 다 같은 사건을 읽어 메일이 두 통 나간다.
    skip_locked 로, 늦게 온 쪽은 먼저 온 쪽이 잡은 사건을 건너뛴다.
    of=('self',) 는 사건의 행만 잠근다. 함께 읽는 계정의 행까지 잠그면 그동안 그 계정의 로그인이 기다린다.
    """
    return list(
        SecurityEvent.objects
        .select_for_update(skip_locked=True, of=('self',))
        .filter(reported_at__isnull=True)
        .select_related('user')
        .order_by('created_at', 'id')[:MAX_EVENTS_PER_DIGEST]
    )


def _mark_reported(events: list[SecurityEvent]) -> None:
    """사건들을 "알렸다" 고 표시한다."""
    ids = [event.pk for event in events]
    SecurityEvent.objects.filter(pk__in=ids).update(reported_at=timezone.now())
