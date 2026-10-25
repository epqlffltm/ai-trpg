# board-server/app/api/me.py

"""
토큰의 주인. 화면이 운영자의 버튼(고정, 신고 처리)을 보일지 정할 때 부른다.

    GET /api/v1/board/me   로그인. {"user_id", "is_operator"}

다른 로그인 API 처럼 토큰의 닉네임을 그 사람의 닉네임으로 적는다(app/core/auth.py).
"""

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.auth import Member

router = APIRouter(prefix='/me', tags=['me'])


class MeResponse(BaseModel):
    """토큰의 주인."""

    user_id: uuid.UUID
    is_operator: bool


@router.get('', response_model=MeResponse, status_code=status.HTTP_200_OK)
async def read_me(member: Member) -> MeResponse:
    """토큰의 주인의 ID 와 운영자인지를 돌려준다."""
    return MeResponse(user_id=member.user_id, is_operator=member.is_operator)
