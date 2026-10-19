# trpg-server/app/events/router.py

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
from app.events.responses import to_event
from app.events.schemas import EventPage

router = APIRouter(prefix='/tables/{table_id}/events', tags=['events'])

# 한 번에 읽는 이벤트의 개수
DEFAULT_EVENT_LIMIT = 50


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
