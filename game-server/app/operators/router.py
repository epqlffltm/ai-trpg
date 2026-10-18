# game-server/app/operators/router.py

"""
운영자 API(#391). 운영자가 남의 테이블과 시나리오를 본다. 읽기만 한다.

주소는 /admin 아래에 따로 묶는다. 일반 사용자의 API 에 섞지 않는다(docs/architecture/operators.md).
  - 운영자(토큰의 roles 에 "operator")가 아니면 404 다. 운영자의 주소가 있다는 것을 알리지 않는다.
  - 모든 주소가 사유(reason, 1~200자)를 받는다. 없으면 422 다. 볼 때마다 감사 기록에 남는다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.assets.routing import MAX_PAGE_SIZE, Paging, Session
from app.assets.scenarios.router import detail_of, to_version_detail
from app.assets.scenarios.schemas import ScenarioDetail, VersionDetail
from app.auth.dependencies import CurrentUser
from app.auth.tokens import AccessClaims
from app.billing.routing import Now, Prices
from app.chat.responses import to_message
from app.chat.schemas import MessagePage
from app.events.responses import to_event
from app.events.schemas import EventPage
from app.operators import service
from app.operators.models import REASON_MAX_LENGTH
from app.operators.schemas import OperatorMember, OperatorTable, OperatorWhisperPage
from app.tables.models import GameTable
from app.whispers.responses import to_whisper

# 한 번에 읽는 기록과 대화의 개수. 앉은 사람의 API 와 같다
DEFAULT_LIMIT = 50


def require_operator(user: CurrentUser) -> AccessClaims:
    """운영자만 통과시킨다. 아니면 404 다(403 이면 운영자의 주소가 있다는 것이 드러난다)."""
    if not user.is_operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not Found')
    return user


Operator = Annotated[AccessClaims, Depends(require_operator)]
# 왜 보는가. 신고 번호나 짧은 글. 공백만 있으면 받지 않는다
Reason = Annotated[str, Query(min_length=1, max_length=REASON_MAX_LENGTH, pattern=r'\S')]
After = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]

router = APIRouter(prefix='/admin', tags=['operators'])


def to_operator_table(table: GameTable) -> OperatorTable:
    """테이블을 운영자가 보는 모양으로 바꾼다. 칸을 하나씩 옮긴다."""
    return OperatorTable(
        id=table.id,
        title=table.title,
        status=table.status,
        rating=table.rating,
        host_id=table.host_id,
        version_id=table.version_id,
        created_at=table.created_at,
        ended_at=table.ended_at,
        members=[OperatorMember(user_id=member.user_id, joined_at=member.joined_at) for member in table.members],
        content=table.content,
    )


@router.get('/tables/{table_id}', response_model=OperatorTable, status_code=status.HTTP_200_OK)
async def read_table(
    table_id: uuid.UUID, operator: Operator, reason: Reason, session: Session, now: Now
) -> OperatorTable:
    """테이블 하나를 굳힌 판의 내용 전부와 함께 본다. 앉아 있지 않아도 된다."""
    table = await service.read_table(session, operator.user_id, table_id, reason, now)
    return to_operator_table(table)


@router.get('/tables/{table_id}/events', response_model=EventPage, status_code=status.HTTP_200_OK)
async def read_events(
    table_id: uuid.UUID,
    operator: Operator,
    reason: Reason,
    session: Session,
    now: Now,
    after: After = 0,
    limit: Limit = DEFAULT_LIMIT,
) -> EventPage:
    """테이블의 기록(서술, 행동, 판정)을 일어난 순서대로 본다. 넘기는 법은 앉은 사람의 것과 같다(after)."""
    table, found = await service.read_events(session, operator.user_id, table_id, reason, now, after, limit)
    return EventPage(items=[to_event(event) for event in found], last_sequence=table.last_sequence)


@router.get('/tables/{table_id}/messages', response_model=MessagePage, status_code=status.HTTP_200_OK)
async def read_messages(
    table_id: uuid.UUID,
    operator: Operator,
    reason: Reason,
    session: Session,
    now: Now,
    after: After = 0,
    limit: Limit = DEFAULT_LIMIT,
) -> MessagePage:
    """테이블 대화를 쓴 순서대로 본다."""
    table, found = await service.read_messages(session, operator.user_id, table_id, reason, now, after, limit)
    return MessagePage(items=[to_message(message) for message in found], last_sequence=table.last_message_sequence)


@router.get('/tables/{table_id}/whispers', response_model=OperatorWhisperPage, status_code=status.HTTP_200_OK)
async def read_whispers(
    table_id: uuid.UUID, operator: Operator, reason: Reason, session: Session, now: Now, paging: Paging
) -> OperatorWhisperPage:
    """테이블의 귓속말 전부를 보낸 순서대로 본다. 누가 누구에게 보냈는지, GM 에게 보였는지가 함께 온다."""
    found, total = await service.read_whispers(
        session, operator.user_id, table_id, reason, now, paging.limit, paging.offset
    )
    return OperatorWhisperPage(items=[to_whisper(whisper) for whisper in found], total=total)


@router.get('/scenarios/{scenario_id}', response_model=ScenarioDetail, status_code=status.HTTP_200_OK)
async def read_scenario(
    scenario_id: uuid.UUID, operator: Operator, reason: Reason, session: Session, prices: Prices, now: Now
) -> ScenarioDetail:
    """남의 시나리오의 초안을 만든 사람이 보는 모양 그대로 본다."""
    scenario = await service.read_scenario(session, operator.user_id, scenario_id, reason, now)
    return await detail_of(session, prices, now, scenario)


@router.get('/scenarios/{scenario_id}/versions/{number}', response_model=VersionDetail, status_code=status.HTTP_200_OK)
async def read_version(
    scenario_id: uuid.UUID, number: int, operator: Operator, reason: Reason, session: Session, now: Now
) -> VersionDetail:
    """남의 시나리오의 판 하나를 굳힌 내용 전부와 함께 본다. 테이블은 이 내용으로 돈다."""
    version = await service.read_version(session, operator.user_id, scenario_id, number, reason, now)
    return to_version_detail(version)
