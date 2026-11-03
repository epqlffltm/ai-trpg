# story-server/app/shortcuts/router.py

"""
세션에서 고를 수 있는 단축어의 목록 API(#981). 입력칸에서 "/"를 치면 보인다.

    GET /api/v1/story/conversations/{id}/shortcuts   [{name, description, source}]  세계관의 것이 먼저, 그 뒤에 내 것

남의 세션은 404(app/conversations/router.py 가 답한다). asset 서버를 쓸 수 없으면 세계관의 것만 싣는다.
부르는 것은 말을 보낼 때다(POST /conversations/{id}/messages 의 "/이름").
"""

import uuid

from fastapi import APIRouter, Request, status

from app.core.dependencies import CurrentViewer, Session
from app.shortcuts import service
from app.shortcuts.schemas import ShortcutOut

router = APIRouter(prefix='/conversations', tags=['shortcuts'])


@router.get('/{conversation_id}/shortcuts', response_model=list[ShortcutOut], status_code=status.HTTP_200_OK)
async def list_shortcuts(
    conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session, request: Request
) -> list[ShortcutOut]:
    """그 세션에서 고를 수 있는 단축어들. 본문은 싣지 않는다."""
    mine = await service.fetch_mine(request.app.state.asset, viewer)
    return await service.available(session, viewer, conversation_id, mine)
