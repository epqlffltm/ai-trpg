# story-server/app/turns/router.py

"""
말을 보내는 API. 바로 SSE(text/event-stream)로 답한다(메시지의 모양은 app/turns/schemas.py).

    POST /api/v1/story/conversations/{id}/messages    {content}  말을 보낸다

응답을 시작하기 전에 거절하는 것은 보통의 오류다(아래 handle_*). 시작한 뒤의 실패는 SSE 의 failed 메시지다.
  - 404: 세션이 없다(남의 것, 볼 수 없는 등급)
  - 409 model_required: 세션에 모델이 없다. 먼저 고른다(PUT /conversations/{id}/model)
  - 409 session_ended: 엔딩을 본 세션이다(세계관이 끝을 골랐다). 읽기만 된다
  - 422 model_unavailable: 모델을 쓸 수 없다(꺼졌다, 은퇴했다, 팔지 않는다). 사람의 말은 저장했을 수 있다
  - 409 generation_in_progress: 이 세션이 다른 답을 쓰는 중이다(app/conversations/router.py 가 답한다)
  - 402 credit_short, gold_required: 크레딧이 모자란다. 사람의 말은 저장했다(message_id)
  - 503 billing_unavailable, provider_unavailable: 잠시 뒤에 다시 한다. 사람의 말은 저장했다(message_id)

요청의 세션(Session)을 쓰지 않는다. 그 세션은 응답이 끝날 때까지 열려 있어서 스트림 내내 연결을 붙잡는다.
모델을 부르는 것은 응답과 따로 도는 작업이다. 앱이 들고 있다가(app.state.turns) 서버가 꺼질 때 멈춘다(app/main.py).
요청과 연결의 메트릭은 SSE 로 센다(sse_*). 요청의 span 과 시간 메트릭에서는 뺀다(app/main.py 의 STREAMS).
chat 서버의 것(chat-server/app/turns/router.py)과 같은 모양이다.
다시 생성, 멈추기, 행동은 그것을 더하는 조각에서 붙인다.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Coroutine
from datetime import datetime

from ai_core.provider import GenerationParams
from conversation_core import sse
from conversation_core.relay import Relay
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from server_core.observability.metrics import measured_stream

from app.core.config import Settings
from app.core.dependencies import CurrentViewer, Now, utc_now
from app.turns import service
from app.turns.charging import CREDIT_SHORT, GOLD_REQUIRED, MODEL_UNAVAILABLE
from app.turns.frames import turn_frame
from app.turns.schemas import MessageCreate
from app.turns.service import ModelRequiredError, SessionEndedError, TurnDeclinedError
from app.turns.values import PromptOptions, TurnStart

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/conversations', tags=['messages'])
# SSE 로 답하는 주소의 설명(API 목록)
SSE_RESPONSES = {200: {'content': {'text/event-stream': {}}, 'description': 'SSE. app/turns/schemas.py 의 메시지들'}}

# 스트림 응답의 머리말. chat 서버의 스트림과 같다.
# no-cache: 중간에서 저장해 두었다가 남에게 주지 않게 한다. X-Accel-Buffering: nginx 가 모았다가 보내지 않게 한다
STREAM_HEADERS = {'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
# 잠시 뒤에 다시 하라는 답의 기다릴 시간(초)
RETRY_AFTER_SECONDS = 5
# 거절의 까닭마다 상태 코드
DECLINED_STATUS = {
    CREDIT_SHORT: status.HTTP_402_PAYMENT_REQUIRED,
    GOLD_REQUIRED: status.HTTP_402_PAYMENT_REQUIRED,
    MODEL_UNAVAILABLE: status.HTTP_422_UNPROCESSABLE_CONTENT,
}
DECLINED_DETAIL = {
    CREDIT_SHORT: '크레딧이 모자랍니다.',
    GOLD_REQUIRED: '이 모델은 골드로만 이용할 수 있습니다.',
    MODEL_UNAVAILABLE: '이 세션에 쓸 수 없는 모델입니다. 모델을 다시 골라 주세요.',
}


def generation_params(settings: Settings) -> GenerationParams:
    """말 한 번의 생성 설정. 길이의 상한과 다양함은 설정에서 온다."""
    return GenerationParams(max_tokens=settings.story_output_limit, temperature=settings.story_temperature)


def prompt_options(settings: Settings) -> PromptOptions:
    """모델에 보낼 메시지의 설정. 지난 말의 양은 설정에서 온다."""
    return PromptOptions(context_chars=settings.story_context_chars)


def keep_running(request: Request, coroutine: Coroutine) -> None:
    """따로 도는 작업을 띄우고 앱이 들고 있게 한다. 끝나면 놓는다. 잡히지 않은 오류는 로그에 남긴다."""
    task = asyncio.create_task(coroutine)
    running: set[asyncio.Task] = request.app.state.turns
    running.add(task)
    task.add_done_callback(running.discard)
    task.add_done_callback(log_failure)


def log_failure(task: asyncio.Task) -> None:
    """작업이 잡히지 않은 오류로 끝났으면 로그에 남긴다. 취소(서버가 꺼진다)는 남기지 않는다."""
    if not task.cancelled() and task.exception() is not None:
        logger.error('말 한 번의 작업이 오류로 끝났습니다', exc_info=task.exception())


async def encode_all(relay: Relay) -> AsyncIterator[str]:
    """통로의 메시지를 SSE 의 글자로. 연결 하나로 센다(끊겨 멈춰도 센다)."""
    with measured_stream():
        async for item in relay.frames():
            yield sse.encode(item)


# --- 예외를 응답으로. 앱에 한 번 등록한다(app/main.py) ---


async def handle_model_required(request: Request, error: ModelRequiredError) -> JSONResponse:
    """세션에 모델이 없으면 409 다. 화면이 모델을 고르게 한다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '먼저 모델을 골라 주세요.', 'code': 'model_required'},
    )


async def handle_session_ended(request: Request, error: SessionEndedError) -> JSONResponse:
    """엔딩을 본 세션이면 409 다. 읽기만 된다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '끝난 이야기입니다.', 'code': 'session_ended'},
    )


async def handle_turn_declined(request: Request, error: TurnDeclinedError) -> JSONResponse:
    """답을 쓰지 않았다. 사람의 말은 저장했다(message_id). 까닭마다 상태 코드가 다르다."""
    status_code = DECLINED_STATUS.get(error.code, status.HTTP_503_SERVICE_UNAVAILABLE)
    detail = DECLINED_DETAIL.get(error.code, '지금은 답할 수 없습니다. 잠시 후 다시 시도해 주세요.')
    headers = {'Retry-After': str(RETRY_AFTER_SECONDS)} if status_code == status.HTTP_503_SERVICE_UNAVAILABLE else None
    content = {'detail': detail, 'code': error.code, 'message_id': str(error.message_id)}
    return JSONResponse(status_code=status_code, content=content, headers=headers)


# --- 스트림 ---


async def stream_turn(request: Request, start: TurnStart, now: datetime) -> StreamingResponse:
    """provider 를 고르고 홀드를 건 뒤 따로 도는 작업을 띄우고 SSE 를 시작한다. 거절되면 TurnDeclinedError."""
    state = request.app.state
    route = await service.prepare_turn(state.session_factory, state.model_router, state.billing, start, now)
    relay = Relay()
    relay.push(turn_frame(start))
    params = generation_params(state.settings)
    keep_running(
        request, service.run_generation(state.session_factory, state.billing, route, start, params, relay, utc_now)
    )
    return StreamingResponse(encode_all(relay), media_type='text/event-stream', headers=STREAM_HEADERS)


# --- 주소 ---


@router.post(
    '/{conversation_id}/messages',
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
    responses=SSE_RESPONSES,
)
async def send_message(
    conversation_id: uuid.UUID, data: MessageCreate, viewer: CurrentViewer, request: Request, now: Now
) -> StreamingResponse:
    """
    말을 보낸다. 사람의 말을 저장하고, 장면의 인물들과 서술의 답을 말 조각으로 흘려보낸다.
    끊겨도 서버는 끝까지 답을 저장한다. 말은 상태(시각, 장소, 호감도)를 바꾸지 않는다.
    """
    state = request.app.state
    options = prompt_options(state.settings)
    start = await service.begin_turn(state.session_factory, viewer, conversation_id, data.content, options, now)
    return await stream_turn(request, start, now)
