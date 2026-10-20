# trpg-server/app/tables/past_router.py

"""
떠난 테이블의 API(#428). 내가 떠난 테이블 목록과, 떠난 때까지의 이벤트를 읽는다. 읽기만 있다.

주소는 /tables/past 아래다. 테이블 하나의 주소(/tables/{table_id})보다 먼저 등록한다(app/main.py).
나중에 등록하면 past 를 테이블의 id 로 읽으려다 422 가 난다.
떠난 적이 없는 테이블은 404 다(app/tables/router.py 의 handle_table_not_found).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.assets.routing import MAX_PAGE_SIZE, Paging, Session
from app.auth.dependencies import CurrentUser
from app.events.responses import to_event
from app.events.schemas import DEFAULT_EVENT_LIMIT, EventPage
from app.tables import past
from app.tables.models import TableDeparture
from app.tables.schemas import PastTableOut, PastTablePage

router = APIRouter(prefix='/tables/past', tags=['tables'])


def to_past_table(departure: TableDeparture, title: str, scenario_id: uuid.UUID) -> PastTableOut:
    """떠난 줄과 테이블의 제목, 시나리오를 응답으로 바꾼다."""
    return PastTableOut(
        table_id=departure.table_id,
        scenario_id=scenario_id,
        title=title,
        character_name=departure.character_name,
        kind=departure.kind,
        last_sequence=departure.last_sequence,
        left_at=departure.left_at,
    )


@router.get('', response_model=PastTablePage, status_code=status.HTTP_200_OK)
async def list_past_tables(user: CurrentUser, session: Session, paging: Paging) -> PastTablePage:
    """내가 떠난 테이블들. 최근에 떠난 것부터다. 시작한 테이블에서 떠난 것만 있다."""
    rows, total = await past.list_past(session, user.user_id, paging.limit, paging.offset)
    return PastTablePage(items=[to_past_table(*row) for row in rows], total=total)


@router.get('/{table_id}/events', response_model=EventPage, status_code=status.HTTP_200_OK)
async def list_past_events(
    table_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_EVENT_LIMIT,
) -> EventPage:
    """
    떠난 테이블의 이벤트를 떠난 때까지만 일어난 순서대로 돌려준다. 앉은 사람의 길(.../events)과 모양이 같다.

    last_sequence 는 떠났다는 이벤트의 번호다. 테이블의 마지막 번호가 아니다. 그 뒤로는 더 오지 않는다.
    """
    departure, events = await past.list_past_events(session, user.user_id, table_id, after, limit)
    return EventPage(items=[to_event(event) for event in events], last_sequence=departure.last_sequence)
