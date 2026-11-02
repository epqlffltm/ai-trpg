# trpg-server/app/campaigns/router.py

"""
캠페인의 플레이 API(#481 B). 요청을 받아 서비스에 넘긴다.

  - POST /campaign-runs: 자기 캠페인의 판으로 플레이를 시작한다. 첫 편의 테이블이 열린다.
  - GET /campaign-runs/{id}: 플레이 하나. 방장과 그 플레이의 테이블에 앉았던 사람, 넘긴 것이 있는 사람만 본다(남은 404).
  - POST /campaign-runs/{id}/next: 방장이 앞 편이 끝난 뒤에 다음 편의 테이블을 연다.
  - POST /campaign-runs/{id}/join: 그 플레이의 사람이 지금 편의 테이블에 초대 코드 없이 앉는다. 넘긴 캐릭터로 앉는다.
"""

import uuid

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser

from app.assets.routing import Session
from app.campaigns import service
from app.campaigns.schemas import RunCreate, RunDetail, RunTable
from app.tables.router import Picker, to_detail
from app.tables.schemas import TableDetail

router = APIRouter(prefix='/campaign-runs', tags=['campaign-runs'])


@router.post('', response_model=RunDetail, status_code=status.HTTP_201_CREATED)
async def start_run(data: RunCreate, user: CurrentUser, session: Session, picker: Picker) -> RunDetail:
    """플레이를 시작한다. 시작한 사람이 첫 편의 테이블의 방장이 된다. 열 수 없는 까닭은 테이블 만들기와 같다."""
    run = await service.start_run(session, user, data, picker)
    return await service.describe(session, run, user.user_id)


@router.get('/{run_id}', response_model=RunDetail, status_code=status.HTTP_200_OK)
async def read_run(run_id: uuid.UUID, user: CurrentUser, session: Session) -> RunDetail:
    """플레이 하나. 편마다의 테이블, 끝난 퀘스트의 결과, 내가 가장 나중에 넘긴 것."""
    run = await service.get_run(session, user.user_id, run_id)
    return await service.describe(session, run, user.user_id)


@router.post('/{run_id}/next', response_model=RunDetail, status_code=status.HTTP_201_CREATED)
async def open_next(
    run_id: uuid.UUID, data: RunTable, user: CurrentUser, session: Session, picker: Picker
) -> RunDetail:
    """
    방장이 다음 편의 테이블을 연다. 방장이 넘긴 캐릭터가 있으면 그것으로 앉는다.

    앞 편이 끝나지 않았으면 409 episode_not_ended, 마지막 편까지 끝났으면 409 run_ended, 방장이 아니면 403.
    """
    run = await service.open_next(session, user, run_id, data, picker)
    return await service.describe(session, run, user.user_id)


@router.post('/{run_id}/join', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def join_run(run_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """그 플레이의 사람이 지금 편의 테이블에 앉는다. 넘긴 캐릭터가 있으면 그것으로 앉는다. 앉는 규칙은 테이블과 같다."""
    table = await service.join_run(session, user, run_id)
    return to_detail(table, user.user_id)
