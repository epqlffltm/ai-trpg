# trpg-server/app/snapshots/router.py

"""
테이블의 장면 그림 API(#983).

    POST /api/v1/game/tables/{table_id}/rounds/{number}/snapshot
        그 라운드의 장면을 그린다. 누른 사람에게 홀드를 건 뒤 202
    GET  /api/v1/game/tables/{table_id}/snapshots
        그 테이블의 그림들(만든 차례). 그리는 중이면 다시 읽는다
    GET  /api/v1/game/tables/{table_id}/snapshots/{id}/image
        그림의 바이트. 이 서버가 asset 서버에서 받아 대신 내준다
    GET  /api/v1/game/snapshots/price
        장면 그림 한 장의 값과 그릴 수 있는지

앉은 사람 누구나 그리고 본다. 값은 누른 사람이 낸다. 그림의 주인도 누른 사람이다(asset 서버의 그 사람의 그림).
그리는 일은 응답과 따로 돈다(app.state.jobs). 서버가 꺼질 때 멈추고 실패로 적어 돈을 돌려준다.

  - 404: 앉지 않은 테이블이다, 라운드가 없다. snapshot_not_found: 그림이 없다(다른 테이블의 것, 다 그리지 않은 것)
  - 422 not_drawable: 장면의 글자가 없는 라운드다
  - 409 snapshot_in_progress: 그 테이블에서 다른 그림을 그리는 중이다
  - 402 credit_short, gold_required: 크레딧이 모자란다
  - 503 snapshot_unavailable: 장면 그림을 만들지 않는 서버이거나 가격표에 없다.
    billing_unavailable·asset_unavailable: 잠시 뒤에 다시
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from server_core.auth.dependencies import CurrentUser, bearer_scheme, unauthorized

from app.assets.routing import Session
from app.billing.routing import Now, Prices, utc_now
from app.snapshots import service
from app.snapshots.charging import CREDIT_SHORT, GOLD_REQUIRED, NOT_FOR_SALE
from app.snapshots.pricing import snapshot_price
from app.snapshots.providers import price_code_of
from app.snapshots.schemas import SnapshotOut, SnapshotPriceOut
from app.snapshots.service import (
    NotDrawableError,
    SnapshotBusyError,
    SnapshotDeclinedError,
    SnapshotNotFoundError,
    SnapshotStart,
    SnapshotUnavailableError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/tables/{table_id}', tags=['snapshots'])
price_router = APIRouter(prefix='/snapshots', tags=['snapshots'])

# 그리는 작업의 종류(app/core/jobs.py). 기본 한도를 쓴다
DRAW_OPERATION = 'snapshot.draw'
# 503 에 싣는 "이만큼 뒤에 다시"(초)
RETRY_AFTER_SECONDS = 5
# 그림을 받은 화면이 들고 있어도 되는 시간(초). 그림은 바뀌지 않는다. 앉은 사람만 받으므로 private 다
IMAGE_MAX_AGE_SECONDS = 3600
# 그릴 수 없다는 까닭. 가격표에 없는 것(팔지 않는다)도 같다
SNAPSHOT_UNAVAILABLE = 'snapshot_unavailable'
DECLINED_STATUS = {CREDIT_SHORT: status.HTTP_402_PAYMENT_REQUIRED, GOLD_REQUIRED: status.HTTP_402_PAYMENT_REQUIRED}
DECLINED_DETAIL = {
    CREDIT_SHORT: '크레딧이 모자랍니다.',
    GOLD_REQUIRED: '장면 그림은 골드로만 만들 수 있습니다.',
}

# 라운드의 번호. 1 부터다
RoundNumber = Annotated[int, Path(ge=1)]


async def get_token(
    user: CurrentUser, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
) -> str:
    """검증한 요청의 토큰. asset 서버에 그림을 맡길 때 그대로 넘긴다("누구의 그림인가"). CurrentUser 가 먼저 본다."""
    if credentials is None:
        raise unauthorized()
    return credentials.credentials


# 누른 사람의 토큰이 드는 API 가 인자의 형식으로 쓴다
Token = Annotated[str, Depends(get_token)]


def keep_drawing(request: Request, start: SnapshotStart, token: str) -> str | None:
    """그리는 일을 작업 관리자에 맡긴다. 자리가 없어 맡지 않았으면 None."""
    state = request.app.state
    job = service.draw_snapshot(
        state.session_factory, state.billing, state.image_provider, state.asset, token, start, utc_now
    )
    return state.jobs.spawn(job, f'snapshot:{start.snapshot_id}', DRAW_OPERATION)


@router.post(
    '/rounds/{number}/snapshot',
    response_model=SnapshotOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def draw(
    table_id: uuid.UUID, number: RoundNumber, user: CurrentUser, token: Token, request: Request
) -> SnapshotOut:
    """그 라운드의 장면 그림을 그리기 시작한다. 홀드가 걸리면 202 이고 그림은 목록에서 받는다."""
    state = request.app.state
    if state.image_provider is None or state.jobs.is_full(DRAW_OPERATION):
        raise SnapshotUnavailableError
    model = state.settings.snapshot_model
    start = await service.begin_snapshot(state.session_factory, user.user_id, table_id, number, model)
    await service.hold_snapshot(state.session_factory, state.billing, start, utc_now())
    if keep_drawing(request, start, token) is None:
        await service.refuse_snapshot(state.session_factory, state.billing, start, utc_now())
    return await service.snapshot_by_id(state.session_factory, start.snapshot_id, user.user_id)


@router.get('/snapshots', response_model=list[SnapshotOut], status_code=status.HTTP_200_OK)
async def list_snapshots(table_id: uuid.UUID, user: CurrentUser, session: Session) -> list[SnapshotOut]:
    """그 테이블의 그림들. 만든 차례다. 누가 그렸든 앉은 사람 모두가 본다."""
    return await service.list_snapshots(session, user.user_id, table_id)


@router.get(
    '/snapshots/{snapshot_id}/image',
    status_code=status.HTTP_200_OK,
    response_class=Response,
    responses={200: {'content': {'image/png': {}, 'image/jpeg': {}, 'image/webp': {}}}},
)
async def read_image(table_id: uuid.UUID, snapshot_id: uuid.UUID, user: CurrentUser, request: Request) -> Response:
    """그림의 바이트. 앉은 사람만 받는다."""
    state = request.app.state
    image = await service.snapshot_image(state.session_factory, state.asset, user.user_id, table_id, snapshot_id)
    headers = {'Cache-Control': f'private, max-age={IMAGE_MAX_AGE_SECONDS}'}
    return Response(content=image.data, media_type=image.mime_type, headers=headers)


@price_router.get('/price', response_model=SnapshotPriceOut, status_code=status.HTTP_200_OK)
async def read_price(user: CurrentUser, request: Request, prices: Prices, now: Now) -> SnapshotPriceOut:
    """장면 그림 한 장의 값. 가격 목록을 받지 못했고 받아 둔 것도 없으면 503 prices_unavailable 이다."""
    state = request.app.state
    book = await prices.book()
    return snapshot_price(book, price_code_of(state.settings.snapshot_model), state.image_provider is not None, now)


# --- 예외를 응답으로. 앱에 한 번 등록한다(app/main.py) ---


def unavailable(code: str = SNAPSHOT_UNAVAILABLE) -> JSONResponse:
    """그릴 수 없다(503)."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={'detail': '지금은 장면 그림을 만들 수 없습니다.', 'code': code},
        headers={'Retry-After': str(RETRY_AFTER_SECONDS)},
    )


async def handle_unavailable(request: Request, error: SnapshotUnavailableError) -> JSONResponse:
    return unavailable()


async def handle_not_drawable(request: Request, error: NotDrawableError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '장면이 있는 라운드만 그림으로 만들 수 있습니다.', 'code': 'not_drawable'},
    )


async def handle_busy(request: Request, error: SnapshotBusyError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '이 테이블에서 다른 그림을 그리는 중입니다.', 'code': 'snapshot_in_progress'},
    )


async def handle_declined(request: Request, error: SnapshotDeclinedError) -> JSONResponse:
    """홀드가 걸리지 않았다. 팔지 않는 가격표면 그릴 수 없는 것으로 답한다."""
    if error.code == NOT_FOR_SALE:
        return unavailable()
    status_code = DECLINED_STATUS.get(error.code, status.HTTP_503_SERVICE_UNAVAILABLE)
    detail = DECLINED_DETAIL.get(error.code, '지금은 장면 그림을 만들 수 없습니다. 잠시 후 다시 시도해 주세요.')
    headers = {'Retry-After': str(RETRY_AFTER_SECONDS)} if status_code == status.HTTP_503_SERVICE_UNAVAILABLE else None
    return JSONResponse(status_code=status_code, content={'detail': detail, 'code': error.code}, headers=headers)


async def handle_not_found(request: Request, error: SnapshotNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={'detail': '장면 그림을 찾을 수 없습니다.', 'code': 'snapshot_not_found'},
    )


async def handle_asset_unavailable(request: Request, error: Exception) -> JSONResponse:
    """asset 서버에 닿지 못했다(그림을 받지 못한다)."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={'detail': '지금은 그림을 받을 수 없습니다. 잠시 후 다시 시도해 주세요.', 'code': 'asset_unavailable'},
        headers={'Retry-After': str(RETRY_AFTER_SECONDS)},
    )
