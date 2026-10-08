# game-server/app/events/router.py

"""
이벤트 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소는 테이블 아래에 둔다(/tables/{table_id}/events). 이벤트는 테이블에 딸린 것이다.
읽기만 있다. 이벤트는 테이블을 바꾸는 API 들이 일하면서 적는다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.assets.routing import MAX_PAGE_SIZE, Session
from app.auth.dependencies import CurrentUser
from app.events import service
from app.events.models import EventType, TableEvent
from app.events.schemas import EventOut, EventPage

router = APIRouter(prefix='/tables/{table_id}/events', tags=['events'])

# 한 번에 읽는 이벤트의 개수
DEFAULT_EVENT_LIMIT = 50

# 종류마다 앉은 사람에게 내보내는 payload 의 칸.
# 여기에 적지 않은 칸은 나가지 않는다. 여기에 없는 종류는 payload 가 통째로 비어서 나간다.
# 나중에 AI 호출이나 GM 만 아는 판정을 이벤트로 적어도, 이 목록에 올리기 전에는 플레이어에게 보이지 않는다
VISIBLE: dict[EventType, tuple[str, ...]] = {
    EventType.TABLE_CREATED: (),
    EventType.MEMBER_JOINED: ('via',),
    EventType.MEMBER_LEFT: ('character_name',),
    EventType.MEMBER_KICKED: ('user_id', 'character_name'),
    EventType.HOST_CHANGED: ('user_id',),
    # 능력치의 굴림도 공개다. 버린 눈까지 모두에게 보인다
    EventType.ABILITIES_ROLLED: ('dice', 'scores', 'times_rolled', 'character_number'),
    EventType.REROLL_GRANTED: ('user_id',),
    EventType.TABLE_STARTED: ('members',),
    EventType.GM_NARRATION: ('text',),
    EventType.ROUND_OPENED: ('number',),
    EventType.PLAYER_ACTION: ('round', 'character_name', 'content', 'action'),
    # 굴림은 공개다. 숫자까지 모두에게 보인다
    EventType.CHECK_ROLLED: (
        'round',
        'character_name',
        'ability',
        'difficulty',
        'roll',
        'modifier',
        'total',
        'target',
        'success',
    ),
    # HP 도 공개다. 앉은 사람은 서로의 시트를 본다
    EventType.HP_CHANGED: (
        'round',
        'user_id',
        'character_name',
        'kind',
        'magnitude',
        'rolls',
        'amount',
        'before',
        'after',
        'max_hp',
        'downed',
    ),
    # 죽음의 굴림도 공개다
    EventType.DEATH_SAVE_ROLLED: (
        'round',
        'user_id',
        'character_name',
        'roll',
        'target',
        'success',
        'successes',
        'failures',
        'fate',
    ),
    EventType.CHARACTER_DIED: ('round', 'user_id', 'character_name', 'cause'),
    # 새 캐릭터의 숫자도 공개다. 시작할 때의 시트를 적는 것과 같다
    EventType.CHARACTER_JOINED: (
        'round',
        'user_id',
        'character_name',
        'replaces',
        'mode',
        'pregen_index',
        'number',
        'sheet',
    ),
    EventType.ROUND_CLOSED: ('number', 'idle'),
    EventType.TABLE_ENDED: (),
}


def visible_payload(event: TableEvent) -> dict:
    """이벤트의 payload 에서 앉은 사람에게 내보내는 칸만 고른다."""
    fields = VISIBLE.get(EventType(event.type), ())
    return {field: event.payload[field] for field in fields if field in event.payload}


def to_event(event: TableEvent) -> EventOut:
    """이벤트를 앉은 사람에게 보여 주는 응답으로 바꾼다. 칸을 하나씩 적어 옮긴다."""
    return EventOut(
        sequence=event.sequence,
        type=event.type,
        actor_id=event.actor_id,
        payload=visible_payload(event),
        caused_by_sequence=event.caused_by_sequence,
        action_group_id=event.action_group_id,
        created_at=event.created_at,
    )


@router.get('', response_model=EventPage, status_code=status.HTTP_200_OK)
async def list_events(
    table_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_EVENT_LIMIT,
) -> EventPage:
    """
    테이블의 이벤트를 일어난 순서대로 돌려준다. after 를 주면 그 번호 뒤의 것만 온다.

    처음에는 after 없이 읽고, 그 뒤로는 마지막으로 받은 번호를 after 로 준다. 못 본 것만 받는다.
    """
    table, events = await service.list_events(session, user.user_id, table_id, after, limit)
    return EventPage(items=[to_event(event) for event in events], last_sequence=table.last_sequence)
