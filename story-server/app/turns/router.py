# story-server/app/turns/router.py

"""
말을 보내고 행동하는 API. 바로 SSE(text/event-stream)로 답한다(메시지의 모양은 app/turns/schemas.py).

    POST /api/v1/story/conversations/{id}/messages    {content}   말을 보낸다
    POST /api/v1/story/conversations/{id}/actions     {kind, …}   행동한다(이동, 시간, 하루 마치기, 선택지, 고백,
                                                                  건네기). 엔진이 판정하고 이어서 모델이 반응을 쓴다
    POST /api/v1/story/messages/{id}/regenerate                   그 말에 다시 답한다. 새 답은 같은 부모 아래의 대안이다
    POST /api/v1/story/messages/{id}/continue                     끊긴 답에 이어 쓴다. 새로 청구한다
    POST /api/v1/story/generations/{id}/stop                      모델을 부르는 것을 멈춘다. 받은 만큼 저장한다. 204

응답을 시작하기 전에 거절하는 것은 보통의 오류다(아래 handle_*). 시작한 뒤의 실패는 SSE 의 failed 메시지다.
  - 404: 세션이 없다(남의 것, 볼 수 없는 등급). 다시 답할 말이 없다(message_not_found)
  - 422 not_regenerable: 다시 쓸 수 없는 말이다(부모가 없는 답)
  - 404 message_not_found, 422 not_editable: 고칠 말(edit_of)이 그 세션에 없다, 사람의 말이 아니다
  - 409 model_required: 세션에 모델이 없다. 먼저 고른다(PUT /conversations/{id}/model)
  - 409 session_ended: 엔딩을 본 세션이다(세계관이 끝을 골랐다). 읽기만 된다
  - 422 not_continuable: 이어 쓸 수 없는 말이다(끊긴 답이 아니다, 지금 가지의 끝이 아니다)
  - 422 cannot_move, no_choice, over, not_in_scene, not_confessable, cooling_down, not_held: 그렇게 할 수 없다
    (app/turns/actions.py). 아무것도 저장하지 않는다
  - 422 model_unavailable: 모델을 쓸 수 없다(꺼졌다, 은퇴했다, 팔지 않는다). 사람의 말은 저장했을 수 있다
  - 409 generation_in_progress: 이 세션이 다른 답을 쓰는 중이다(app/conversations/router.py 가 답한다)
  - 402 credit_short, gold_required: 크레딧이 모자란다. 사람의 말은 저장했다(message_id)
  - 503 billing_unavailable, provider_unavailable: 잠시 뒤에 다시 한다. 사람의 말은 저장했다(message_id)

요청의 세션(Session)을 쓰지 않는다. 그 세션은 응답이 끝날 때까지 열려 있어서 스트림 내내 연결을 붙잡는다.
모델을 부르는 것은 응답과 따로 도는 작업이다. 앱이 들고 있다가(app.state.turns) 서버가 꺼질 때 멈춘다(app/main.py).
요청과 연결의 메트릭은 SSE 로 센다(sse_*). 요청의 span 과 시간 메트릭에서는 뺀다(app/main.py 의 STREAMS).
chat 서버의 것(chat-server/app/turns/router.py)과 같은 모양이다.
router 와 message_router 의 주소는 모두 모델을 부르므로 사람마다 요청 수를 센다(app/limits/).
넘으면 429 too_many_attempts 다.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Coroutine
from datetime import datetime
from typing import Annotated

from ai_core.provider import GenerationParams
from conversation_core import sse
from conversation_core.relay import Relay
from fastapi import APIRouter, Body, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from server_core.observability.metrics import measured_stream

from app.core.config import Settings
from app.core.dependencies import CurrentViewer, Now, utc_now
from app.limits.routing import GENERATION_LIMIT
from app.turns import service
from app.turns.actions import ActionRefusedError, to_engine
from app.turns.charging import CREDIT_SHORT, GOLD_REQUIRED, MODEL_UNAVAILABLE
from app.turns.frames import turn_frame
from app.turns.schemas import ActionCreate, MessageCreate
from app.turns.service import (
    MessageNotFoundError,
    ModelRequiredError,
    NotContinuableError,
    NotRegenerableError,
    SessionEndedError,
    TurnDeclinedError,
)
from app.turns.stops import StopSwitch
from app.turns.values import PromptOptions, TurnStart

logger = logging.getLogger(__name__)

# 이 두 라우터의 주소는 모두 모델을 부른다. 사람마다 요청 수를 센다(app/limits/). 멈추기는 세지 않는다
router = APIRouter(prefix='/conversations', tags=['messages'], dependencies=[GENERATION_LIMIT])
message_router = APIRouter(prefix='/messages', tags=['messages'], dependencies=[GENERATION_LIMIT])
generation_router = APIRouter(prefix='/generations', tags=['messages'])
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
    return PromptOptions(context_chars=settings.story_context_chars, suggestions=settings.story_suggestions)


def keep_running(request: Request, start: TurnStart, stop: StopSwitch, coroutine: Coroutine) -> None:
    """
    따로 도는 작업을 띄우고 앱이 들고 있게 한다. 멈추는 스위치는 기록의 id 로 찾게 둔다(app.state.stops).
    끝나면 둘 다 놓는다. 잡히지 않은 오류는 로그에 남긴다. 끝나면 그 세션을 요약할지 본다.
    """
    task = asyncio.create_task(coroutine)
    running: set[asyncio.Task] = request.app.state.turns
    stops: dict[uuid.UUID, tuple[uuid.UUID, StopSwitch]] = request.app.state.stops
    running.add(task)
    stops[start.generation_id] = (start.owner_id, stop)
    task.add_done_callback(running.discard)
    task.add_done_callback(lambda _: stops.pop(start.generation_id, None))
    task.add_done_callback(log_failure)
    task.add_done_callback(lambda done: summarize_after(request, start, done))


def summarize_after(request: Request, start: TurnStart, task: asyncio.Task) -> None:
    """말 한 번이 끝나면(서버가 꺼져 멈추지 않았으면) 그 세션을 요약할지 보러 간다(app/memory/summarizer.py)."""
    if not task.cancelled():
        request.app.state.summarizer.request(start.conversation_id)


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


async def handle_message_not_found(request: Request, error: MessageNotFoundError) -> JSONResponse:
    """다시 답할 말이 없으면 404 다(남의 것도 없는 것과 같다)."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={'detail': '말을 찾을 수 없습니다.', 'code': 'message_not_found'},
    )


async def handle_not_continuable(request: Request, error: NotContinuableError) -> JSONResponse:
    """이어 쓸 수 없는 말이면 422 다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '이어 쓸 수 없는 말입니다.', 'code': 'not_continuable'},
    )


async def handle_not_regenerable(request: Request, error: NotRegenerableError) -> JSONResponse:
    """다시 쓸 수 없는 말이면 422 다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '다시 쓸 수 없는 말입니다.', 'code': 'not_regenerable'},
    )


async def handle_session_ended(request: Request, error: SessionEndedError) -> JSONResponse:
    """엔딩을 본 세션이면 409 다. 읽기만 된다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '끝난 이야기입니다.', 'code': 'session_ended'},
    )


async def handle_action_refused(request: Request, error: ActionRefusedError) -> JSONResponse:
    """할 수 없는 행동이면 422 다. code 가 까닭이다. 아무것도 저장하지 않았다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '그렇게 할 수 없습니다.', 'code': error.code},
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
    stop = StopSwitch()
    run = service.run_generation(
        state.session_factory, state.billing, route, start, params, relay, utc_now, stop, state.lore_recall
    )
    keep_running(request, start, stop, run)
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
    edit_of 가 있으면 그 사람의 말을 고친 새 가지다(원본은 남는다). 사람의 말이 아니면 422 not_editable,
    그 세션의 말이 아니면 404 message_not_found 다.
    """
    state = request.app.state
    options = prompt_options(state.settings)
    start = await service.begin_turn(
        state.session_factory, viewer, conversation_id, data.content, options, now, data.edit_of
    )
    return await stream_turn(request, start, now)


@router.post(
    '/{conversation_id}/actions',
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
    responses=SSE_RESPONSES,
)
async def act(
    conversation_id: uuid.UUID,
    data: Annotated[ActionCreate, Body()],
    viewer: CurrentViewer,
    request: Request,
    now: Now,
) -> StreamingResponse:
    """
    행동한다. 이동(move), 시간 보내기(pass_time), 하루 마치기(end_day), 선택지 고르기(choose), 고백(confess),
    건네기(give).
    엔진이 할 수 있는지 보고 상태를 바꾼 뒤(이벤트가 열리고 엔딩을 볼 수 있다), 모델의 반응을 흘려보낸다.
    반응을 받으니 한 번 청구한다. turn 의 user_message 가 행동 말(role action)이고 state 가 그 뒤의 상태다.
    SSE 의 모양은 말 보내기와 같다.
    """
    state = request.app.state
    options = prompt_options(state.settings)
    start = await service.begin_action(state.session_factory, viewer, conversation_id, to_engine(data), options, now)
    return await stream_turn(request, start, now)


@message_router.post(
    '/{message_id}/regenerate',
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
    responses=SSE_RESPONSES,
)
async def regenerate(message_id: uuid.UUID, viewer: CurrentViewer, request: Request, now: Now) -> StreamingResponse:
    """
    그 말에 다시 답한다. 답이면 같은 말(사람의 말이나 행동 말)에 새 대안을, 사람의 말이나 행동 말이면(답을 못 받았다)
    그 말에 답을 쓴다. 엔진은 다시 판정하지 않는다. 그 말의 상태와, 그 말에 적힌 이벤트와 엔딩의 장면으로 쓴다.

    새 호출이라 새로 청구한다. 앞의 답은 남고, 세션의 가지는 새 답으로 옮겨 간다. SSE 의 모양은 말 보내기와 같다.
    """
    state = request.app.state
    start = await service.begin_regenerate(
        state.session_factory, viewer, message_id, prompt_options(state.settings), now
    )
    return await stream_turn(request, start, now)


@message_router.post(
    '/{message_id}/continue',
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
    responses=SSE_RESPONSES,
)
async def continue_message(
    message_id: uuid.UUID, viewer: CurrentViewer, request: Request, now: Now
) -> StreamingResponse:
    """
    끊긴 답(partial)에 이어 쓴다. 지금 가지의 끝인 답만 된다. 엔진은 다시 판정하지 않는다.

    새 호출이라 새로 청구한다. SSE 의 turn 에 continues(그 답의 id)가 실린다.
    첫 segment 앞의 delta 는 그 답의 마지막 조각에 붙는 글이고, segment 가 오면 새 조각이다.
    done 의 말은 이어 붙인 그 답 전체다. 다 쓰면 complete, 또 끊기면 partial 이라 다시 이어 쓸 수 있다.
    """
    state = request.app.state
    start = await service.begin_continue(state.session_factory, viewer, message_id, prompt_options(state.settings), now)
    return await stream_turn(request, start, now)


@generation_router.post('/{generation_id}/stop', status_code=status.HTTP_204_NO_CONTENT)
async def stop_generation(generation_id: uuid.UUID, viewer: CurrentViewer, request: Request) -> Response:
    """
    모델을 부르는 것을 멈춘다(공급자의 호출도 끊는다).
    받은 만큼 partial 로 저장하고 청구한다. 받은 조각이 없으면 반환한다.

    멈출 생성이 없으면(끝났다, 남의 것이다, 이 서버에서 도는 것이 아니다) 404 generation_not_running 이다.
    """
    found = request.app.state.stops.get(generation_id)
    if found is None or found[0] != viewer.claims.user_id or not found[1].request():
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={'detail': '멈출 답이 없습니다.', 'code': 'generation_not_running'},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
