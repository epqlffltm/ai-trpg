# auth-server/accounts/security_events.py

"""
보안 이벤트를 기록한다.

기록할지 말지는 부르는 쪽이 정한다. 여기는 적기만 한다.
막힌 뒤에도 계속 들어오는 요청마다 적으면, 공격자가 요청 수만큼 DB 에 행을 쌓을 수 있다.
그래서 부르는 쪽은 "막히기 시작한 순간" 에만 부른다(attempt_limits 가 그 순간을 알려 준다).

적은 이벤트마다 로그 한 줄(warning, error_code security.event)도 남긴다(#25). 로그 모으기(Loki)에서 다른 줄과
같은 request_id, trace_id 로 이어 본다. 원본은 DB 의 줄이다. 로그는 14일 뒤 사라지고 DB 는 보관 기간까지 남는다.
  - 저장(커밋)한 뒤에 남긴다. 되돌린 이벤트의 줄이 남지 않는다. 트랜잭션 밖이면 바로 남긴다.
  - 싣는 것은 종류, 이벤트의 번호, 대상 계정의 공개 ID 다. IP 와 운영자의 사유(note)는 싣지 않는다.
    필요하면 번호로 DB(관리 화면)에서 본다. 로그는 더 오래, 더 넓게 퍼지는 곳이라 개인정보를 덜 싣는다.
"""

import logging
from functools import partial

from django.db import transaction

from accounts.models import SecurityEvent, User

logger = logging.getLogger(__name__)

# 보안 이벤트의 줄에 붙이는 코드(docs/observability.md 의 "오류 코드"). 종류는 security_event 칸에 싣는다
SECURITY_EVENT_CODE = 'security.event'


def record_security_event(*, kind: str, ip: str = '', user: User | None = None, note: str = '') -> None:
    """보안 이벤트 하나를 남긴다. note 는 운영자가 남긴 사유다(계정 정지와 풀기). 저장한 뒤에 로그 한 줄을 남긴다."""
    event = SecurityEvent.objects.create(kind=kind, ip=ip, user=user, note=note)
    transaction.on_commit(partial(log_security_event, event))


def log_security_event(event: SecurityEvent) -> None:
    """적은 이벤트 하나를 로그 한 줄로 남긴다. 종류, 번호, 대상 계정의 공개 ID 만 싣는다."""
    fields = {'error_code': SECURITY_EVENT_CODE, 'security_event': event.kind, 'security_event_id': event.pk}
    if event.user is not None:
        fields['user_id'] = str(event.user.public_id)
    logger.warning('보안 이벤트를 남겼습니다: %s', event.kind, extra=fields)


def find_user_by_username(username: str) -> User | None:
    """
    로그인에 입력된 아이디의 주인을 찾는다. 없으면 None 이다.

    이벤트에 대상 계정을 적기 위해서만 쓴다. 로그인 판정에는 쓰지 않는다.
    """
    return User.objects.filter(username=username.strip()).first()
