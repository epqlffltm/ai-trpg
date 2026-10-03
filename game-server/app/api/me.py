# game-server/app/api/me.py

"""
토큰의 주인이 누구인지 돌려주는 API.

인증 서버가 발급한 토큰을 이 서버가 검증할 수 있는지 확인하는 가장 작은 API 다.
게임 서버는 사용자의 이름이나 이메일을 모른다. 인증 서버의 public_id 만 안다.
"""

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser

router = APIRouter(tags=['me'])


class MeResponse(BaseModel):
    # 인증 서버의 public_id
    user_id: uuid.UUID


@router.get('/me', response_model=MeResponse, status_code=status.HTTP_200_OK)
async def read_me(user: CurrentUser) -> MeResponse:
    """토큰이 유효하면 그 주인의 ID 를 돌려준다."""
    return MeResponse(user_id=user.user_id)
