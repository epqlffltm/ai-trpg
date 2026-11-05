# trpg-server/app/portraits/router.py

"""
제작자의 캐릭터 그림 API(#983). 프리젠에 붙일 그림을 올리고 본다.

    POST /api/v1/game/portraits
        그림을 올린다. 본문은 그림 파일의 바이트 그대로다(multipart 가 아니다). 201
    GET  /api/v1/game/portraits
        내가 올린 그림들. ?limit=&offset=. 최근 것부터
    GET  /api/v1/game/portraits/{id}/image
        내가 올린 그림의 바이트. 이 서버가 asset 서버에서 받아 대신 내준다

  - 413 image_too_large: 본문이 상한(PORTRAIT_MAX_BYTES)을 넘는다. asset 의 상한을 넘어도 같다
  - 415 image_format: PNG, JPEG, WebP 가 아니다. 422 image_unreadable: 열 수 없는 그림이다
  - 409 portrait_limit: 올릴 수 있는 수를 다 채웠다
  - 404 portrait_not_found: 내가 올린 그림이 아니다
  - 503 asset_unavailable: asset 서버를 쓸 수 없다(설정이 없는 서버 포함)
"""

import uuid

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser

from app.asset_server.client import ImageRejectedError
from app.assets.routing import Paging, Session
from app.portraits import service
from app.portraits.schemas import PortraitOut, PortraitPage
from app.portraits.service import PortraitLimitError, PortraitNotFoundError
from app.snapshots.router import Token

router = APIRouter(prefix='/portraits', tags=['portraits'])

# 그림을 받은 화면이 들고 있어도 되는 시간(초). 그림은 바뀌지 않는다. 올린 사람만 받으므로 private 다
IMAGE_MAX_AGE_SECONDS = 3600
# asset 이 그림을 받지 않은 까닭마다의 응답
REJECTED_STATUS = {
    'image_too_large': status.HTTP_413_CONTENT_TOO_LARGE,
    'image_format': status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    'image_unreadable': status.HTTP_422_UNPROCESSABLE_CONTENT,
}
REJECTED_DETAIL = {
    'image_too_large': '그림이 너무 큽니다.',
    'image_format': 'PNG, JPEG, WebP 그림만 올릴 수 있습니다.',
    'image_unreadable': '그림을 열 수 없습니다.',
}


class BodyTooLargeError(Exception):
    """본문이 상한을 넘는다."""


def declared_too_large(request: Request, limit: int) -> bool:
    """머리말(Content-Length)이 상한을 넘는다고 말하는가. 그러면 읽기 전에 거절한다."""
    declared = request.headers.get('content-length')
    return declared is not None and declared.isdigit() and int(declared) > limit


async def read_limited(request: Request, limit: int) -> bytes:
    """본문을 읽는다. 상한을 넘으면 끝까지 읽지 않고 BodyTooLargeError."""
    if declared_too_large(request, limit):
        raise BodyTooLargeError
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise BodyTooLargeError
    return bytes(body)


# --- 서비스의 예외를 응답으로 바꾼다. 앱에 한 번 등록한다(app/main.py) ---


async def handle_too_large(request: Request, error: BodyTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        content={'detail': REJECTED_DETAIL['image_too_large'], 'code': 'image_too_large'},
    )


async def handle_rejected(request: Request, error: ImageRejectedError) -> JSONResponse:
    """asset 서버가 그림을 받지 않았다. 까닭을 그대로 싣는다."""
    return JSONResponse(
        status_code=REJECTED_STATUS.get(error.code, status.HTTP_422_UNPROCESSABLE_CONTENT),
        content={'detail': REJECTED_DETAIL.get(error.code, '그림을 열 수 없습니다.'), 'code': error.code},
    )


async def handle_limit(request: Request, error: PortraitLimitError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            'detail': f'캐릭터 그림은 {service.PORTRAIT_MAX_PER_OWNER}장까지 올릴 수 있습니다.',
            'code': 'portrait_limit',
        },
    )


async def handle_not_found(request: Request, error: PortraitNotFoundError) -> JSONResponse:
    """남의 그림도 404 다. 403 을 주면 그 id 의 그림이 있다는 것이 드러난다."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.', 'code': 'portrait_not_found'}
    )


# --- 주소 ---


@router.post('', response_model=PortraitOut, status_code=status.HTTP_201_CREATED)
async def upload(user: CurrentUser, token: Token, request: Request) -> PortraitOut:
    """그림을 올린다. 로그인을 먼저 보고, 그다음 본문을 읽는다."""
    state = request.app.state
    data = await read_limited(request, state.settings.portrait_max_bytes)
    return await service.upload_portrait(state.session_factory, state.asset, token, user.user_id, data)


@router.get('', response_model=PortraitPage, status_code=status.HTTP_200_OK)
async def list_mine(user: CurrentUser, session: Session, paging: Paging) -> PortraitPage:
    """내가 올린 그림들. 최근 것부터다."""
    return await service.list_portraits(session, user.user_id, paging.limit, paging.offset)


@router.get(
    '/{portrait_id}/image',
    status_code=status.HTTP_200_OK,
    response_class=Response,
    responses={200: {'content': {'image/png': {}, 'image/jpeg': {}, 'image/webp': {}}}},
)
async def read_image(portrait_id: uuid.UUID, user: CurrentUser, request: Request) -> Response:
    """내가 올린 그림의 바이트."""
    state = request.app.state
    image = await service.portrait_image(state.session_factory, state.asset, user.user_id, portrait_id)
    headers = {'Cache-Control': f'private, max-age={IMAGE_MAX_AGE_SECONDS}'}
    return Response(content=image.data, media_type=image.mime_type, headers=headers)
