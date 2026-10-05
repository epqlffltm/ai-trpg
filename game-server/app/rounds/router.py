# game-server/app/rounds/router.py

"""
라운드 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소는 테이블 아래에 둔다(/tables/{table_id}/rounds). 라운드는 테이블에 딸린 것이다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse

from app.assets.routing import Paging, Session
from app.auth.dependencies import CurrentUser
from app.rounds import service
from app.rounds.models import Round
from app.rounds.narrator import Narrator
from app.rounds.schemas import DeclarationOut, DeclarationUpdate, RoundOut, RoundPage
from app.rounds.service import RoundConflictError, RoundNotFoundError
from app.tables.models import GameTable, TableStatus

router = APIRouter(prefix='/tables/{table_id}/rounds', tags=['rounds'])


def get_narrator(request: Request) -> Narrator:
    """앱에 꽂아 둔 서술자를 꺼낸다(app/main.py). 테스트와 운영이 다른 서술자를 꽂을 수 있다."""
    return request.app.state.narrator


# 라운드를 닫을 수 있는 API 가 인자의 형식으로 쓴다
Narrating = Annotated[Narrator, Depends(get_narrator)]

# 라운드의 번호. 1 부터다
RoundNumber = Annotated[int, Path(ge=1)]


def to_round(table: GameTable, round_: Round, viewer_id: uuid.UUID) -> RoundOut:
    """
    라운드를 앉은 사람에게 보여 주는 응답으로 바꾼다.

    열려 있는 라운드에서는 남의 선언의 글을 가린다. 누가 냈는지만 보인다. 닫히면 모두의 글이 보인다.
    """
    is_open = round_.closed_at is None
    declarations = [
        DeclarationOut(
            user_id=declaration.user_id,
            character_name=declaration.character_name,
            content=declaration.content if not is_open or declaration.user_id == viewer_id else None,
        )
        for declaration in round_.declarations
    ]
    # 진행 중인 테이블의 열린 라운드에서만 기다리는 사람이 있다
    is_waiting = is_open and table.status == TableStatus.PLAYING
    return RoundOut(
        number=round_.number,
        scene=round_.scene,
        is_open=is_open,
        declarations=declarations,
        waiting_for=service.waiting_for(table, round_) if is_waiting else [],
        created_at=round_.created_at,
        closed_at=round_.closed_at,
    )


# --- 서비스의 예외를 응답으로 바꾼다. 앱에 한 번 등록한다(app/main.py) ---


async def handle_round_not_found(request: Request, error: RoundNotFoundError) -> JSONResponse:
    """ "그런 번호의 라운드가 없다"는 404 다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '라운드를 찾을 수 없습니다.'})


async def handle_round_conflict(request: Request, error: RoundConflictError) -> JSONResponse:
    """ "테이블의 지금 상태와 부딪힌다"는 409 다. 이유를 reason 에 싣는다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '테이블의 지금 상태에서는 할 수 없습니다.', 'reason': error.reason},
    )


# --- 읽기 ---


@router.get('', response_model=RoundPage, status_code=status.HTTP_200_OK)
async def list_rounds(table_id: uuid.UUID, user: CurrentUser, session: Session, paging: Paging) -> RoundPage:
    """테이블의 라운드를 처음 것부터 돌려준다. 지나간 이야기를 순서대로 읽는다."""
    table, rounds, total = await service.list_rounds(session, user.user_id, table_id, paging.limit, paging.offset)
    return RoundPage(items=[to_round(table, round_, user.user_id) for round_ in rounds], total=total)


# /current 를 /{number} 보다 먼저 적는다. 먼저 적은 주소가 먼저 맞춰진다
@router.get('/current', response_model=RoundOut, status_code=status.HTTP_200_OK)
async def read_current_round(table_id: uuid.UUID, user: CurrentUser, session: Session) -> RoundOut:
    """가장 최근 라운드를 돌려준다. 진행 중인 테이블에서는 지금 선언을 받고 있는 라운드다."""
    table, round_ = await service.get_current_round(session, user.user_id, table_id)
    return to_round(table, round_, user.user_id)


@router.get('/{number}', response_model=RoundOut, status_code=status.HTTP_200_OK)
async def read_round(table_id: uuid.UUID, number: RoundNumber, user: CurrentUser, session: Session) -> RoundOut:
    """라운드 하나를 번호로 돌려준다."""
    table, round_ = await service.get_round(session, user.user_id, table_id, number)
    return to_round(table, round_, user.user_id)


# --- 바꾸기 ---


@router.put('/current/declaration', response_model=RoundOut, status_code=status.HTTP_200_OK)
async def declare(
    table_id: uuid.UUID, data: DeclarationUpdate, user: CurrentUser, session: Session, narrator: Narrating
) -> RoundOut:
    """
    열려 있는 라운드에 선언을 낸다. 다시 내면 바뀐다.

    돌려주는 것은 가장 최근 라운드다. 모두가 내서 라운드가 닫혔으면, 새로 열린 라운드가 온다.
    """
    table, round_ = await service.declare(session, user.user_id, table_id, data, narrator)
    return to_round(table, round_, user.user_id)


@router.post('/current/close', response_model=RoundOut, status_code=status.HTTP_200_OK)
async def close_round(table_id: uuid.UUID, user: CurrentUser, session: Session, narrator: Narrating) -> RoundOut:
    """방장이 열려 있는 라운드를 닫는다. 선언을 기다리지 않고 다음 라운드로 넘어간다."""
    table, round_ = await service.force_close(session, user.user_id, table_id, narrator)
    return to_round(table, round_, user.user_id)
