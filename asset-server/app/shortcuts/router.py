# asset-server/app/shortcuts/router.py

"""
내 단축어 API(#981). 로그인한 사람의 것만 다룬다.

    GET /api/v1/asset/shortcuts   {items: [{name, description, body}]}  적지 않았으면 빈 목록
    PUT /api/v1/asset/shortcuts   {items: [...]}  통째로 바꾼다. 같은 이름, 20개 넘음, 길이 넘음은 422

다른 서버(chat, story)가 말을 보낼 때 가져가는 길은 app/shortcuts/supply.py 다.
"""

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser

from app.core.dependencies import Session
from app.shortcuts import service
from app.shortcuts.schemas import ShortcutList

router = APIRouter(prefix='/shortcuts', tags=['shortcuts'])


@router.get('', response_model=ShortcutList, status_code=status.HTTP_200_OK)
async def read_shortcuts(user: CurrentUser, session: Session) -> ShortcutList:
    """내 단축어들."""
    return ShortcutList(items=await service.list_shortcuts(session, user.user_id))


@router.put('', response_model=ShortcutList, status_code=status.HTTP_200_OK)
async def replace_shortcuts(data: ShortcutList, user: CurrentUser, session: Session) -> ShortcutList:
    """내 단축어를 통째로 바꾼다."""
    return ShortcutList(items=await service.replace_shortcuts(session, user.user_id, data.items))
