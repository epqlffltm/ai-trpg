# game-server/app/tables/router.py

"""
테이블 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

응답을 만들 때 테이블의 복사본에서 참가자에게 보여도 되는 것만 꺼낸다(to_detail).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.assets.routing import Paging, Session
from app.assets.scenarios.schemas import RecommendedPlayers
from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.auth.dependencies import CurrentUser
from app.tables import service
from app.tables.models import GameTable, TableMember
from app.tables.schemas import (
    CharacterOut,
    CharacterUpdate,
    HostTransfer,
    JoinRequest,
    LobbyJoinRequest,
    MemberOut,
    PregenChoice,
    TableCreate,
    TableDetail,
    TablePage,
    TableSummary,
)
from app.tables.service import (
    MemberNotFoundError,
    NotHostError,
    TableConflictError,
    TableNotFoundError,
    TableOptionError,
    WrongPasswordError,
)

router = APIRouter(prefix='/tables', tags=['tables'])


def to_summary(table: GameTable) -> TableSummary:
    """테이블을 목록용 응답으로 바꾼다."""
    return TableSummary(
        id=table.id,
        title=table.title,
        status=table.status,
        rating=table.rating,
        capacity=table.capacity,
        member_count=len(table.members),
        host_id=table.host_id,
        is_public=table.is_public,
        has_password=table.password_hash is not None,
        created_at=table.created_at,
    )


def to_member(table: GameTable, member: TableMember) -> MemberOut:
    """앉은 사람 하나를 응답으로 바꾼다."""
    character = None
    if member.character_name is not None:
        character = CharacterOut(name=member.character_name, description=member.character_description)
    return MemberOut(
        user_id=member.user_id,
        is_host=member.user_id == table.host_id,
        character=character,
        pregen_index=member.pregen_index,
        joined_at=member.joined_at,
    )


def to_pregen_choices(table: GameTable, snapshot: Snapshot) -> list[PregenChoice]:
    """프리젠마다 누가 가져갔는지를 붙여 응답으로 바꾼다."""
    taken_by = {member.pregen_index: member.user_id for member in table.members if member.pregen_index is not None}
    return [
        PregenChoice(name=pregen.name, description=pregen.description, taken_by=taken_by.get(index))
        for index, pregen in enumerate(snapshot.pregens)
    ]


def to_detail(table: GameTable, viewer_id: uuid.UUID) -> TableDetail:
    """
    테이블을 참가자에게 보여 주는 응답으로 바꾼다. 여기 적은 칸만 나간다.

    viewer_id 는 보는 사람이다. 초대 코드는 방장에게만 싣는다.
    """
    snapshot = read_snapshot(table.content)
    return TableDetail(
        **to_summary(table).model_dump(),
        opening=snapshot.openings[table.opening_index],
        recommended_players=RecommendedPlayers(**snapshot.recommended_players.model_dump()),
        pregens=to_pregen_choices(table, snapshot),
        members=[to_member(table, member) for member in table.members],
        invite_code=table.invite_code if viewer_id == table.host_id else None,
        started_at=table.started_at,
        ended_at=table.ended_at,
    )


# --- 서비스의 예외를 응답으로 바꾼다. 앱에 한 번 등록한다(app/main.py) ---


async def handle_table_not_found(request: Request, error: TableNotFoundError) -> JSONResponse:
    """
    "그런 테이블이 없다"는 404 다.

    앉지 않은 사람에게도, 초대 코드가 틀린 사람에게도 404 다. 403 을 주면 그 테이블이 있다는 것이 드러난다.
    """
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '테이블을 찾을 수 없습니다.'})


async def handle_member_not_found(request: Request, error: MemberNotFoundError) -> JSONResponse:
    """ "그 사람은 이 테이블에 없다"는 404 다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '참가자를 찾을 수 없습니다.'})


async def handle_not_host(request: Request, error: NotHostError) -> JSONResponse:
    """
    "방장만 할 수 있다"는 403 이다.

    여기서는 403 을 써도 된다. 이 응답을 받는 사람은 테이블에 앉아 있어서, 테이블이 있다는 것을 이미 안다.
    """
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={'detail': '방장만 할 수 있습니다.'})


async def handle_wrong_password(request: Request, error: WrongPasswordError) -> JSONResponse:
    """
    "비밀번호가 틀렸다"는 403 이다.

    404 가 아니다. 로비에 보이는 테이블이라 있다는 것은 누구나 안다.
    """
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={'detail': '비밀번호가 맞지 않습니다.'})


async def handle_table_conflict(request: Request, error: TableConflictError) -> JSONResponse:
    """ "테이블의 지금 상태와 부딪힌다"는 409 다. 이유를 reason 에 싣는다. 화면이 이 값으로 안내를 고른다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '테이블의 지금 상태에서는 할 수 없습니다.', 'reason': error.reason},
    )


async def handle_table_option(request: Request, error: TableOptionError) -> JSONResponse:
    """ "고른 번호가 판에 없다"는 422 다. 주소는 맞고, 본문에 적은 값이 틀렸다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': f'{error.field} 가 가리키는 것이 없습니다.'},
    )


# --- 만들기, 들어가기, 읽기 ---


@router.post('', response_model=TableDetail, status_code=status.HTTP_201_CREATED)
async def create_table(data: TableCreate, user: CurrentUser, session: Session) -> TableDetail:
    """테이블을 만든다. 만든 사람이 방장이 되어 앉는다."""
    table = await service.create_table(session, user, data)
    return to_detail(table, user.user_id)


@router.post('/join', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def join_table(data: JoinRequest, user: CurrentUser, session: Session) -> TableDetail:
    """초대 코드로 테이블에 들어가 앉는다."""
    table = await service.join_table(session, user, data)
    return to_detail(table, user.user_id)


@router.get('', response_model=TablePage, status_code=status.HTTP_200_OK)
async def list_tables(user: CurrentUser, session: Session, paging: Paging) -> TablePage:
    """내가 앉아 있는 테이블을 최근에 만든 것부터 돌려준다."""
    tables, total = await service.list_tables(session, user.user_id, paging.limit, paging.offset)
    return TablePage(items=[to_summary(table) for table in tables], total=total)


# 로비를 시나리오로 거르는 값. 주소의 ?scenario_id=.. 에서 읽는다
ScenarioFilter = Annotated[uuid.UUID | None, Query()]


# /lobby 를 /{table_id} 보다 먼저 적는다. 먼저 적은 주소가 먼저 맞춰진다
@router.get('/lobby', response_model=TablePage, status_code=status.HTTP_200_OK)
async def list_lobby(
    user: CurrentUser, session: Session, paging: Paging, scenario_id: ScenarioFilter = None
) -> TablePage:
    """로비. 들어갈 수 있는 테이블을 최근에 만든 것부터 돌려준다. 모집 중이고 자리가 남은 것만 나온다."""
    tables, total = await service.list_lobby(session, user, scenario_id, paging.limit, paging.offset)
    return TablePage(items=[to_summary(table) for table in tables], total=total)


@router.get('/{table_id}', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def read_table(table_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """내가 앉아 있는 테이블 하나를 돌려준다."""
    table = await service.get_table(session, user.user_id, table_id)
    return to_detail(table, user.user_id)


@router.post('/{table_id}/join', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def join_public_table(
    table_id: uuid.UUID, data: LobbyJoinRequest, user: CurrentUser, session: Session
) -> TableDetail:
    """로비에 보이는 테이블에 들어가 앉는다. 비밀번호가 걸려 있으면 비밀번호를 보낸다."""
    table = await service.join_public_table(session, user, table_id, data)
    return to_detail(table, user.user_id)


# --- 참가자가 하는 일 ---


@router.put('/{table_id}/character', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def set_character(table_id: uuid.UUID, data: CharacterUpdate, user: CurrentUser, session: Session) -> TableDetail:
    """내 캐릭터를 정한다. 직접 만들거나 프리젠을 가져온다. 모집 중에만 된다."""
    table = await service.set_character(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


# /members/me 를 /members/{user_id} 보다 먼저 적는다. 먼저 적은 주소가 먼저 맞춰진다
@router.delete('/{table_id}/members/me', status_code=status.HTTP_204_NO_CONTENT)
async def leave_table(table_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """테이블에서 나간다. 방장이 나가면 가장 먼저 들어온 사람이 방장이 된다."""
    await service.leave_table(session, user.user_id, table_id)


# --- 방장이 하는 일 ---


@router.delete('/{table_id}/members/{user_id}', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def kick_member(table_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """참가자를 내보낸다. 초대 코드가 새로 만들어진다. 응답에 새 코드가 실린다."""
    table = await service.kick_member(session, user.user_id, table_id, user_id)
    return to_detail(table, user.user_id)


@router.put('/{table_id}/host', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def transfer_host(table_id: uuid.UUID, data: HostTransfer, user: CurrentUser, session: Session) -> TableDetail:
    """방장을 다른 참가자에게 넘긴다."""
    table = await service.transfer_host(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


@router.post('/{table_id}/start', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def start_table(table_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """테이블을 시작한다. 모든 참가자가 캐릭터를 만들어 둬야 한다."""
    table = await service.start_table(session, user.user_id, table_id)
    return to_detail(table, user.user_id)


@router.post('/{table_id}/end', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def end_table(table_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """테이블을 끝낸다."""
    table = await service.end_table(session, user.user_id, table_id)
    return to_detail(table, user.user_id)
