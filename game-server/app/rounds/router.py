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
from app.core.dice import Rolling
from app.rounds import service
from app.rounds.closing import RoundCloser
from app.rounds.models import Declaration, Round, RoundStatus
from app.rounds.schemas import DeclarationOut, DeclarationUpdate, RoundOut, RoundPage
from app.rounds.service import ActionNotInRulesError, ActionTargetError, RoundConflictError, RoundNotFoundError
from app.tables.models import GameTable, TableStatus

router = APIRouter(prefix='/tables/{table_id}/rounds', tags=['rounds'])


def get_closer(request: Request) -> RoundCloser:
    """
    서술을 뒤에서 돌게 맡기는 것을 만든다. 앱에 꽂아 둔 서술자와 작업 관리자를 쓴다(app/main.py).

    요청마다 새로 만든다. 테스트가 서술자를 바꿔 꽂으면 그 뒤의 요청부터 바뀐 것을 쓴다.
    """
    state = request.app.state
    return RoundCloser(
        session_factory=state.session_factory,
        narrator=state.narrator,
        jobs=state.jobs,
        lore=state.lore,
        memories=state.memories,
        histories=state.histories,
    )


# 라운드를 닫을 수 있는 API 가 인자의 형식으로 쓴다
Closing = Annotated[RoundCloser, Depends(get_closer)]

# 라운드의 번호. 1 부터다
RoundNumber = Annotated[int, Path(ge=1)]


def to_round(table: GameTable, round_: Round, viewer_id: uuid.UUID) -> RoundOut:
    """
    라운드를 앉은 사람에게 보여 주는 응답으로 바꾼다.

    선언을 받는 동안에는 남의 선언의 글과 행동을 가린다. 누가 냈는지만 보인다.
    선언을 마감하면(닫는 중부터) 모두의 것이 보인다. 그때는 이벤트 기록에도 적혀 있다.
    """
    is_open = round_.status == RoundStatus.OPEN

    def can_see(declaration: Declaration) -> bool:
        """보는 사람이 이 선언의 글과 행동을 볼 수 있는가."""
        return not is_open or declaration.user_id == viewer_id

    declarations = [
        DeclarationOut(
            user_id=declaration.user_id,
            character_name=declaration.character_name,
            content=declaration.content if can_see(declaration) else None,
            action=declaration.action if can_see(declaration) else None,
            # 결과는 가리지 않는다. 열려 있는 동안에는 어차피 없고, 마감한 뒤에는 모두에게 보인다
            outcome=declaration.outcome,
        )
        for declaration in round_.declarations
    ]
    # 진행 중인 테이블에서 선언을 받는 중일 때만 기다리는 사람이 있다
    is_waiting = is_open and table.status == TableStatus.PLAYING
    return RoundOut(
        number=round_.number,
        scene=round_.scene,
        status=round_.status,
        declarations=declarations,
        # 죽음의 굴림은 가리지 않는다. 열려 있는 동안에는 어차피 없고, 마감한 뒤에는 모두에게 보인다
        death_saves=round_.death_saves,
        arrivals=round_.arrivals,
        waiting_for=service.waiting_for(table, round_) if is_waiting else [],
        created_at=round_.created_at,
        closing_at=round_.closing_at,
        closed_at=round_.closed_at,
        narration_failed_at=round_.narration_failed_at,
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


async def handle_action_not_in_rules(request: Request, error: ActionNotInRulesError) -> JSONResponse:
    """ "행동이 이 테이블의 규칙에 없는 것을 가리킨다"는 422 다. 모양은 맞고, 적은 값이 틀렸다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': f'action.{error.field} 가 이 테이블의 규칙에 없습니다.'},
    )


async def handle_action_target(request: Request, error: ActionTargetError) -> JSONResponse:
    """ "행동의 대상이 이 테이블에 앉은 사람이 아니다"는 422 다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': 'action.target 이 이 테이블에 앉은 사람이 아닙니다.'},
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
    table_id: uuid.UUID, data: DeclarationUpdate, user: CurrentUser, session: Session, closer: Closing, dice: Rolling
) -> RoundOut:
    """
    열려 있는 라운드에 선언을 낸다. 다시 내면 바뀐다.

    모두가 내면 라운드가 닫기 시작한다. 그때는 status 가 closing 인 라운드가 돌아온다.
    행동을 붙인 선언은 그때 판정된다. 결과가 선언의 outcome 에 실려 돌아온다.
    GM 의 서술은 뒤에서 돈다. 끝나서 다음 라운드가 열린 것은 스트림으로 온다.
    """
    table, round_ = await service.declare(session, user.user_id, table_id, data, closer, dice)
    return to_round(table, round_, user.user_id)


# 202: 접수했다는 뜻이다. 일은 아직 끝나지 않았다. 서술이 뒤에서 돈다
@router.post('/current/close', response_model=RoundOut, status_code=status.HTTP_202_ACCEPTED)
async def close_round(
    table_id: uuid.UUID, user: CurrentUser, session: Session, closer: Closing, dice: Rolling
) -> RoundOut:
    """
    방장이 라운드를 닫는다. 선언을 기다리지 않고 넘어간다. status 가 closing 인 라운드가 돌아온다.

    닫는 중인 채로 오래 멈춰 있는 라운드에 다시 부르면 서술을 다시 맡긴다. 판정은 다시 하지 않는다.
    """
    table, round_ = await service.force_close(session, user.user_id, table_id, closer, dice)
    return to_round(table, round_, user.user_id)
