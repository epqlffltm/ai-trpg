# chat-server/app/snapshots/router.py

"""
장면 그림 API(#983).

    POST /api/v1/chat/messages/{id}/snapshot          그 답의 장면 그림을 그린다. 홀드를 건 뒤 202(그리는 중)
    GET  /api/v1/chat/snapshots/price                 장면 그림 한 장의 값과 그릴 수 있는지
    GET  /api/v1/chat/conversations/{id}/snapshots    그 대화의 그림들(만든 차례). 그리는 중이면 다시 읽는다

그림은 asset 서버의 주소(GET /api/v1/asset/images/{image_id})로 받는다. 주인만 본다(토큰을 실어 받는다).
그리는 일은 응답과 따로 돈다(app.state.snapshot_tasks). 서버가 꺼질 때 멈추고 실패로 적어 돈을 돌려준다.

  - 404: 말이 없다(남의 대화의 말). 남의 대화의 목록도 404 다
  - 422 not_drawable: 캐릭터의 글자가 있는 답이 아니다
  - 409 snapshot_in_progress: 그 대화에서 다른 그림을 그리는 중이다
  - 402 credit_short, gold_required: 크레딧이 모자란다
  - 503 snapshot_unavailable: 장면 그림을 만들지 않는 서버이거나 가격표에 없다. billing_unavailable: 잠시 뒤에
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.billing.routing import Prices
from app.core.dependencies import CurrentViewer, Now, Session, utc_now
from app.limits.routing import GENERATION_LIMIT
from app.snapshots import service
from app.snapshots.pricing import snapshot_price
from app.snapshots.providers import price_code_of
from app.snapshots.schemas import SnapshotOut, SnapshotPriceOut
from app.snapshots.service import (
    NotDrawableError,
    SnapshotBusyError,
    SnapshotDeclinedError,
    SnapshotStart,
    SnapshotUnavailableError,
)
from app.turns.charging import CREDIT_SHORT, GOLD_REQUIRED, MODEL_UNAVAILABLE

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/messages', tags=['snapshots'])
conversation_router = APIRouter(prefix='/conversations', tags=['snapshots'])
price_router = APIRouter(prefix='/snapshots', tags=['snapshots'])

# 503 에 싣는 "이만큼 뒤에 다시"(초)
RETRY_AFTER_SECONDS = 5
# 그릴 수 없다는 까닭. 가격표에 없는 것(팔지 않는다)도 같다
SNAPSHOT_UNAVAILABLE = 'snapshot_unavailable'
DECLINED_STATUS = {CREDIT_SHORT: status.HTTP_402_PAYMENT_REQUIRED, GOLD_REQUIRED: status.HTTP_402_PAYMENT_REQUIRED}
DECLINED_DETAIL = {
    CREDIT_SHORT: '크레딧이 모자랍니다.',
    GOLD_REQUIRED: '장면 그림은 골드로만 만들 수 있습니다.',
}


def log_failure(task: asyncio.Task) -> None:
    """따로 도는 작업이 잡지 못한 오류로 끝났으면 로그에 남긴다."""
    if not task.cancelled() and task.exception() is not None:
        logger.error('장면 그림의 작업이 오류로 끝났습니다', exc_info=task.exception())


def keep_drawing(request: Request, start: SnapshotStart, token: str) -> None:
    """그리는 일을 띄우고 앱이 들고 있게 한다. 끝나면 놓는다."""
    state = request.app.state
    coroutine = service.draw_snapshot(
        state.session_factory, state.billing, state.image_provider, state.asset, token, start, utc_now
    )
    task = asyncio.create_task(coroutine)
    running: set[asyncio.Task] = state.snapshot_tasks
    running.add(task)
    task.add_done_callback(running.discard)
    task.add_done_callback(log_failure)


@router.post(
    '/{message_id}/snapshot',
    response_model=SnapshotOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[GENERATION_LIMIT],
)
async def draw(message_id: uuid.UUID, viewer: CurrentViewer, request: Request) -> SnapshotOut:
    """그 답의 장면 그림을 그리기 시작한다. 홀드가 걸리면 202 이고 그림은 목록에서 받는다."""
    state = request.app.state
    if state.image_provider is None:
        raise SnapshotUnavailableError
    model = state.settings.snapshot_model
    start = await service.begin_snapshot(state.session_factory, viewer, message_id, model)
    await service.hold_snapshot(state.session_factory, state.billing, start, utc_now())
    keep_drawing(request, start, viewer.token)
    return await service.snapshot_by_id(state.session_factory, start.snapshot_id)


@conversation_router.get(
    '/{conversation_id}/snapshots', response_model=list[SnapshotOut], status_code=status.HTTP_200_OK
)
async def list_snapshots(conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session) -> list[SnapshotOut]:
    """그 대화의 그림들. 만든 차례다."""
    return await service.list_snapshots(session, viewer, conversation_id)


@price_router.get('/price', response_model=SnapshotPriceOut, status_code=status.HTTP_200_OK)
async def read_price(viewer: CurrentViewer, request: Request, prices: Prices, now: Now) -> SnapshotPriceOut:
    """장면 그림 한 장의 값. 가격 목록을 받지 못했고 받아 둔 것도 없으면 503 prices_unavailable 이다."""
    state = request.app.state
    book = await prices.book()
    return snapshot_price(book, price_code_of(state.settings.snapshot_model), state.image_provider is not None, now)


# --- 예외를 응답으로. 앱에 한 번 등록한다(app/main.py) ---


def unavailable() -> JSONResponse:
    """그릴 수 없다(503)."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={'detail': '지금은 장면 그림을 만들 수 없습니다.', 'code': SNAPSHOT_UNAVAILABLE},
        headers={'Retry-After': str(RETRY_AFTER_SECONDS)},
    )


async def handle_unavailable(request: Request, error: SnapshotUnavailableError) -> JSONResponse:
    return unavailable()


async def handle_not_drawable(request: Request, error: NotDrawableError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '캐릭터의 답만 그림으로 만들 수 있습니다.', 'code': 'not_drawable'},
    )


async def handle_busy(request: Request, error: SnapshotBusyError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '이 대화에서 다른 그림을 그리는 중입니다.', 'code': 'snapshot_in_progress'},
    )


async def handle_declined(request: Request, error: SnapshotDeclinedError) -> JSONResponse:
    """홀드가 걸리지 않았다. 팔지 않는 가격표면 그릴 수 없는 것으로 답한다."""
    if error.code == MODEL_UNAVAILABLE:
        return unavailable()
    status_code = DECLINED_STATUS.get(error.code, status.HTTP_503_SERVICE_UNAVAILABLE)
    detail = DECLINED_DETAIL.get(error.code, '지금은 장면 그림을 만들 수 없습니다. 잠시 후 다시 시도해 주세요.')
    headers = {'Retry-After': str(RETRY_AFTER_SECONDS)} if status_code == status.HTTP_503_SERVICE_UNAVAILABLE else None
    return JSONResponse(status_code=status_code, content={'detail': detail, 'code': error.code}, headers=headers)
