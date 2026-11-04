# asset-server/app/images/supply.py

"""
다른 서버(chat, story)가 만든 장면 그림을 맡기고 지우는 주소(#983). 그 서버의 서명과 사용자의 토큰을 함께 본다.

    POST   /api/v1/asset/service/{caller}/images              본문은 그림의 바이트. 토큰의 주인의 그림으로 올린다. 201
    DELETE /api/v1/asset/service/{caller}/images/{image_id}   토큰의 주인의 그림을 지운다(대화를 지울 때). 204

  - 서명이 틀리면 401 이다. 토큰보다 먼저 본다. 서명은 받은 바이트 그대로 본다(그림의 바이트까지)
  - 맡긴 그림은 사용자가 올린 그림과 같다. 다시 인코딩하고(받지 않는 형식 415, 열 수 없으면 422, 상한을 넘으면 413),
    주인만 본다(GET /images/{id}). 공급자가 준 바이트를 그대로 내주지 않는다
  - 지우기는 남의 것, 없는 것, 판에 쓰인 것이면 아무 일도 하지 않고 204 다(어느 것인지 알리지 않는다)
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from server_core.auth.dependencies import CurrentUser

from app.core.dependencies import Session
from app.core.service_auth import SignedImageBody, verify_caller
from app.images import service
from app.images.router import Decoder, Store, to_detail
from app.images.schemas import ImageDetail

router = APIRouter(prefix='/service/{caller}/images', tags=['service'])


def utc_now() -> datetime:
    """지금(UTC). 저장소의 서명에 쓴다."""
    return datetime.now(UTC)


@router.post('', response_model=ImageDetail, status_code=status.HTTP_201_CREATED)
async def keep_image(
    data: SignedImageBody, user: CurrentUser, session: Session, store: Store, decoder: Decoder
) -> ImageDetail:
    """만든 그림을 토큰의 주인의 그림으로 올린다."""
    image = await service.upload_image(session, store, decoder, user.user_id, data, utc_now())
    return to_detail(image)


@router.delete('/{image_id}', status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_caller)])
async def discard_image(image_id: uuid.UUID, user: CurrentUser, session: Session, store: Store) -> None:
    """토큰의 주인의 그림을 지운다. 지울 것이 없어도 204 다."""
    await service.discard_image(session, store, user.user_id, image_id, utc_now())
