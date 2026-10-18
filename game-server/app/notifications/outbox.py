# game-server/app/notifications/outbox.py

"""
발송함에 알림을 적는다. 저장(commit)은 부른 쪽이 그 일과 함께 한다(app/notifications/models.py).

테이블의 이벤트를 방장에게 알리는 것(tell_host)도 여기 있다. 지금 알리는 것은 서술 모델의 은퇴 셋이다
(app/tables/model_retirement.py). 모델을 바꿀 수 있는 사람이 방장이라 방장에게만 보낸다.
앉은 사람은 같은 이름의 테이블 이벤트로 이미 본다.

열쇠(source_key)는 "<kind>:<테이블>:<이벤트의 번호>" 다. 이벤트의 번호는 테이블 안에서 하나라서
은퇴 예정의 네 단계(30, 14, 7, 1 일 전)가 서로 다른 알림이 되고, 같은 이벤트를 다시 보내면 같은 열쇠다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import EventType, TableEvent
from app.notifications.models import OutgoingNotification
from app.tables.models import GameTable

# 방장에게 알리는 테이블의 이벤트와 그 알림의 종류
HOST_NOTICES = {
    EventType.NARRATION_MODEL_RETIRING: 'narration_model.retiring',
    EventType.NARRATION_MODEL_REPLACED: 'narration_model.replaced',
    EventType.NARRATION_MODEL_UNAVAILABLE: 'narration_model.unavailable',
}


def put(session: AsyncSession, user_id: uuid.UUID, kind: str, source_key: str, payload: dict) -> OutgoingNotification:
    """발송함에 알림 하나를 적는다. 저장하지 않는다. 바로 보낼 차례다."""
    notification = OutgoingNotification(user_id=user_id, kind=kind, source_key=source_key, payload=payload)
    session.add(notification)
    return notification


def event_key(kind: str, event: TableEvent) -> str:
    """테이블의 이벤트에서 온 알림의 열쇠. 같은 이벤트면 같은 열쇠다."""
    return f'{kind}:{event.table_id}:{event.sequence}'


def table_payload(table: GameTable, event: TableEvent) -> dict:
    """
    테이블의 이벤트를 알림의 내용으로 만든다. 이벤트의 내용에 어느 테이블인지(ID 와 제목)를 붙인다.

    알림함은 게임 서버를 부르지 않고 보여 줄 수 있어야 해서 제목을 함께 싣는다. 판의 내용(GM 전용 글)은 싣지 않는다.
    """
    return {'table_id': str(table.id), 'title': table.title, **event.payload}


def tell_host(session: AsyncSession, table: GameTable, event: TableEvent) -> OutgoingNotification:
    """테이블의 이벤트를 방장에게 알린다. 알리는 이벤트가 아니면 KeyError 다(부른 쪽의 버그)."""
    kind = HOST_NOTICES[event.type]
    return put(session, table.host_id, kind, event_key(kind, event), table_payload(table, event))
