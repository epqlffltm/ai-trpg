# asset-server/app/images/router.py

"""
그림 API(#566). 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

  - POST /images: 그림을 올린다. 본문은 그림 파일의 바이트 그대로다(multipart 가 아니다). 로그인해야 한다.
    형식은 요청의 Content-Type 이 아니라 파일의 머리로 본다. 크기 상한은 설정(IMAGE_MAX_BYTES, 기본 10MB)이다.
  - GET /images/{id}: 볼 수 있으면 본문 없이 200 과 X-Accel-Redirect, X-Image-Source 를 답한다.
    nginx 가 그 머리말을 보고 저장소에서 받아 캐시하고 내준다. 프록시 없이 부르면 빈 200 이다.
    볼 수 없으면(없는 그림 포함) 404 다. 토큰은 없어도 된다. 공개 캐릭터에 쓰인 전체 이용가의 그림은 누구나 본다.
    브라우저의 img 는 Authorization 머리말을 싣지 못한다. 주인만 보는 그림(페르소나, 초안)과 성인 등급의 그림은
    화면이 토큰을 실어 받아(fetch) 보여 준다.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser, OptionalUser

from app.core.dependencies import AppSettings, Session
from app.core.service_auth import read_body
from app.images import service
from app.images.isolation import ImageDecoder, ImageUnreadableError
from app.images.models import Image
from app.images.schemas import ImageDetail
from app.images.service import ImageNotFoundError, ImageNotOwnedError, UnsupportedImageError
from app.images.store import ImageStore, ImageStoreUnavailableError

router = APIRouter(prefix='/images', tags=['images'])


def get_image_store(request: Request) -> ImageStore:
    """앱의 그림 저장소(app/images/setup.py)."""
    return request.app.state.image_store


def get_image_decoder(request: Request) -> ImageDecoder:
    """앱의 그림을 여는 것(app/images/setup.py)."""
    return request.app.state.image_decoder


Store = Annotated[ImageStore, Depends(get_image_store)]
Decoder = Annotated[ImageDecoder, Depends(get_image_decoder)]


def utc_now() -> datetime:
    """지금(UTC). 저장소의 서명에 쓴다."""
    return datetime.now(UTC)


def to_detail(image: Image) -> ImageDetail:
    """그림을 응답의 모양으로 바꾼다."""
    return ImageDetail(
        id=image.id,
        format=image.format,
        byte_size=image.byte_size,
        width=image.width,
        height=image.height,
        url=service.image_url(image.id),
        created_at=image.created_at,
    )


async def handle_unsupported_image(request: Request, error: UnsupportedImageError) -> JSONResponse:
    """받는 형식이 아니면 415 다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        content={'detail': 'PNG, JPEG, WebP 그림만 올릴 수 있습니다.', 'code': 'image_format'},
    )


async def handle_unreadable_image(request: Request, error: ImageUnreadableError) -> JSONResponse:
    """열 수 없는 그림(망가졌거나, 머리만 흉내 냈거나, 너무 크게 풀린다)은 422 다. 까닭은 나누지 않는다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '그림을 열 수 없습니다.', 'code': 'image_unreadable'},
    )


async def handle_image_not_found(request: Request, error: ImageNotFoundError) -> JSONResponse:
    """없거나 볼 수 없는 그림은 404 다. 프록시가 저장소에서 찾지 못했을 때와 같은 본문이다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.'})


async def handle_image_not_owned(request: Request, error: ImageNotOwnedError) -> JSONResponse:
    """남의 그림이나 없는 그림을 붙이려 하면 422 다(페르소나와 캐릭터의 image_id)."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '자기가 올린 그림만 붙일 수 있습니다.', 'code': 'image_not_owned'},
    )


async def handle_store_unavailable(request: Request, error: ImageStoreUnavailableError) -> JSONResponse:
    """저장소에 닿지 못했거나 저장소가 없는 서버면 503 이다. 화면은 잠시 뒤 다시 올리게 한다."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={'detail': '그림 저장소를 쓸 수 없습니다. 잠시 뒤 다시 시도하세요.', 'code': 'image_store_unavailable'},
    )


@router.post('', response_model=ImageDetail, status_code=status.HTTP_201_CREATED)
async def upload_image(
    request: Request, user: CurrentUser, session: Session, settings: AppSettings, store: Store, decoder: Decoder
) -> ImageDetail:
    """그림을 올린다. 본문은 그림 파일의 바이트다. 로그인을 먼저 보고, 그다음 본문을 읽는다."""
    data = await read_body(request, settings.image_max_bytes)
    image = await service.upload_image(session, store, decoder, user.user_id, data, utc_now())
    return to_detail(image)


@router.get(
    '/{image_id}',
    status_code=status.HTTP_200_OK,
    response_class=Response,
    responses={
        status.HTTP_200_OK: {'description': '본문 없음. X-Accel-Redirect 와 X-Image-Source 로 nginx 가 그림을 내준다'},
        status.HTTP_404_NOT_FOUND: {'description': '없거나 볼 수 없는 그림'},
    },
)
async def serve_image(image_id: uuid.UUID, viewer: OptionalUser, session: Session, store: Store) -> Response:
    """볼 수 있으면 nginx 에 넘길 머리말을 답한다. 그림의 바이트는 nginx 가 저장소에서 받아 내준다."""
    image = await service.viewable_image(session, viewer, image_id)
    return Response(status_code=status.HTTP_200_OK, headers=service.accel_headers(store, image, utc_now()))
