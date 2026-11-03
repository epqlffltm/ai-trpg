# asset-server/app/shortcuts/supply.py

"""
내 단축어를 다른 서버에 내주는 주소(#981). 그 서버의 서명(app/core/service_auth.py)과 사용자의 토큰을 함께 본다.

    GET /api/v1/asset/service/{caller}/shortcuts   토큰의 주인의 단축어들

  - 서명이 틀리면 401 이다. 토큰보다 먼저 본다(라우터의 의존성)
  - 판이 없다. 부르는 쪽은 말을 보낼 때마다 읽는다(그 턴에 "/이름"이 있을 때만)
"""

from fastapi import APIRouter, Depends, status
from server_core.auth.dependencies import CurrentUser

from app.core.dependencies import Session
from app.core.service_auth import verify_caller
from app.shortcuts import service
from app.shortcuts.schemas import ShortcutList

router = APIRouter(prefix='/service/{caller}/shortcuts', tags=['service'], dependencies=[Depends(verify_caller)])


@router.get('', response_model=ShortcutList, status_code=status.HTTP_200_OK)
async def supply_shortcuts(user: CurrentUser, session: Session) -> ShortcutList:
    """토큰의 주인의 단축어들."""
    return ShortcutList(items=await service.list_shortcuts(session, user.user_id))
