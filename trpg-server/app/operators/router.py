# trpg-server/app/operators/router.py

"""
운영자 API. 운영자가 남의 테이블과 시나리오를 보고(#391), 제재한다(#392).

주소는 /admin 아래에 따로 묶는다. 일반 사용자의 API 에 섞지 않는다(docs/architecture/operators.md).
  - 운영자(토큰의 roles 에 "operator")가 아니면 404 다. 운영자의 주소가 있다는 것을 알리지 않는다.
  - 모든 주소가 사유(reason, 1~200자)를 받는다. 없으면 422 다. 볼 때는 쿼리로, 제재할 때는 본문으로 받는다.
    볼 때마다, 제재할 때마다 감사 기록에 남는다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser
from server_core.auth.tokens import AccessClaims

from app.assets.routing import MAX_PAGE_SIZE, Paging, Session
from app.assets.scenarios.router import detail_of, to_version_detail
from app.assets.scenarios.schemas import ScenarioDetail, VersionDetail
from app.billing.routing import Now, Prices
from app.chat.responses import to_message
from app.chat.schemas import MessagePage
from app.events.responses import to_event
from app.events.schemas import EventPage
from app.operators import sanctions, service
from app.operators.models import REASON_MAX_LENGTH, PublishingBan
from app.operators.publishing import PublicationRefusedError
from app.operators.sanctions import SanctionConflictError
from app.operators.schemas import (
    ActionRequest,
    OperatorMember,
    OperatorTable,
    OperatorWhisperPage,
    PublishingBanOut,
    SanctionOut,
)
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


# --- 제재(#392) ---


def ban_threshold(request: Request) -> int:
    """공개 금지에 닿는 제재의 수. 설정(PUBLISHING_BAN_THRESHOLD)에서 읽는다."""
    return request.app.state.settings.publishing_ban_threshold


Threshold = Annotated[int, Depends(ban_threshold)]


def to_ban(ban: PublishingBan) -> PublishingBanOut:
    """공개 금지의 줄을 응답으로 바꾼다."""
    return PublishingBanOut(
        user_id=ban.user_id,
        banned=ban.lifted_at is None,
        banned_at=ban.banned_at,
        banned_by=ban.banned_by,
        lifted_at=ban.lifted_at,
    )


@router.post('/scenarios/{scenario_id}/sanction', response_model=SanctionOut, status_code=status.HTTP_201_CREATED)
async def sanction_scenario(
    scenario_id: uuid.UUID,
    data: ActionRequest,
    operator: Operator,
    session: Session,
    now: Now,
    threshold: Threshold,
) -> SanctionOut:
    """
    공개 중인 판을 제재한다. 공개를 내리고 그 판을 다시 공개하지 못하게 한다. 제작자는 혼자서는 계속 쓴다.

    공개 중인 판이 없으면 409(not_published). 제작자의 제재가 정해진 수에 닿으면 저절로 공개 금지가 된다.
    """
    result = await sanctions.sanction_scenario(session, operator.user_id, scenario_id, data.reason, now, threshold)
    return SanctionOut(
        scenario_id=result.scenario_id,
        version_number=result.version_number,
        owner_id=result.owner_id,
        publishing_banned=result.publishing_banned,
    )


@router.post('/tables/{table_id}/end', response_model=OperatorTable, status_code=status.HTTP_200_OK)
async def end_table(
    table_id: uuid.UUID, data: ActionRequest, operator: Operator, session: Session, now: Now
) -> OperatorTable:
    """테이블을 끝낸다. 앉은 사람에게는 "운영자가 끝냈다"가 보인다. 이미 끝났으면 409(already_ended)."""
    table = await sanctions.end_table(session, operator.user_id, table_id, data.reason, now)
    return to_operator_table(table)


@router.post('/users/{user_id}/publishing-ban', response_model=PublishingBanOut, status_code=status.HTTP_200_OK)
async def ban_publisher(
    user_id: uuid.UUID, data: ActionRequest, operator: Operator, session: Session, now: Now
) -> PublishingBanOut:
    """한 사람의 공개를 금지한다. 이미 금지 중이면 409(already_banned). 플레이는 막지 않는다."""
    return to_ban(await sanctions.ban_publisher(session, operator.user_id, user_id, data.reason, now))


@router.post('/users/{user_id}/publishing-ban/lift', response_model=PublishingBanOut, status_code=status.HTTP_200_OK)
async def lift_ban(
    user_id: uuid.UUID, data: ActionRequest, operator: Operator, session: Session, now: Now
) -> PublishingBanOut:
    """공개 금지를 푼다. 금지 중이 아니면 409(not_banned). 그 뒤의 제재부터 다시 센다."""
    return to_ban(await sanctions.lift_ban(session, operator.user_id, user_id, data.reason, now))


async def handle_sanction_conflict(request: Request, error: SanctionConflictError) -> JSONResponse:
    """ "제재가 지금 상태와 부딪힌다"는 409 다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '지금 상태에서는 할 수 없습니다.', 'reason': error.reason},
    )


async def handle_publication_refused(request: Request, error: PublicationRefusedError) -> JSONResponse:
    """
    제작자가 공개하지 못하는 것은 403 이다(#392). 화면이 까닭을 알리게 code 를 싣는다. 앱에 한 번 등록한다.

    version_sanctioned 면 고쳐서 새 판을 내면 된다. publishing_banned 면 운영자가 풀 때까지 공개하지 못한다.
    """
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={'detail': '이 판은 공개할 수 없습니다.', 'code': error.code},
    )
