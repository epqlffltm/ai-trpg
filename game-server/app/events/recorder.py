# game-server/app/events/recorder.py

"""
이벤트를 적는다. 이벤트가 생기는 길은 이 파일의 record 하나뿐이다.

테이블을 바꾸는 서비스들(app/tables/service.py, app/rounds/service.py)이 부른다.
커밋하지 않는다. 부른 쪽이 상태를 바꾼 것과 함께 커밋한다. 그래서 상태만 바뀌거나 기록만 남는 일이 없다.

읽는 쪽(app/events/service.py)과 파일을 나눈 이유: 읽는 쪽은 "앉은 사람인가"를 테이블 서비스에 묻는다.
적는 쪽까지 한 파일에 있으면 테이블 서비스와 서로를 불러오게 된다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import repository
from app.events.models import EventType, TableEvent
from app.tables.models import GameTable


def next_sequence(table: GameTable) -> int:
    """
    이 테이블의 다음 이벤트 번호를 받는다. 테이블이 세고 있는 번호를 하나 올린다.

    테이블을 잠근 뒤에 부른다. 잠그지 않으면 두 요청이 같은 번호를 받는다(그때는 DB 의 유일 조건이 막는다).
    """
    table.last_sequence += 1
    return table.last_sequence


def record(
    session: AsyncSession,
    table: GameTable,
    type_: EventType,
    *,
    actor_id: uuid.UUID | None = None,
    payload: dict | None = None,
    group: uuid.UUID | None = None,
    cause: TableEvent | None = None,
) -> TableEvent:
    """
    이벤트 하나를 적는다. 적은 이벤트를 돌려준다. 저장하지는 않는다.

    actor_id: 이 일을 한 사람. 사람이 한 일이 아니면 주지 않는다.
    payload: 종류마다 다른 내용. JSON 에 넣을 수 있는 값만 넣는다(UUID 는 글자로 바꿔서).
    cause: 이 이벤트를 일으킨 이벤트. 주면 원인으로 잇고, 원인과 같은 묶음에 넣는다.
    group: 묶음. cause 가 없는데 다른 이벤트와 한 묶음이어야 할 때 준다. 둘 다 없으면 혼자 한 묶음이다.

    테이블이 이미 저장돼 있어야 한다(table.id 가 있어야 한다).
    """
    if cause is not None:
        group = cause.action_group_id
    event = TableEvent(
        table_id=table.id,
        sequence=next_sequence(table),
        type=type_,
        actor_id=actor_id,
        payload=payload or {},
        caused_by_sequence=cause.sequence if cause else None,
        action_group_id=group or uuid.uuid4(),
    )
    repository.add_event(session, event)
    return event
