# chat-server/app/gallery/router.py

"""
내가 연 이벤트 씬(#669). 소개(C2)의 이벤트 씬 칸과 갤러리(C7)가 읽는다.

    GET /api/v1/chat/gallery    내가 연 것. ?character_id=&limit=&offset=. 최근에 연 것부터

해금 대상인 이벤트 씬만 적힌다. 가지를 바꾸거나 대화를 지워도 남는다.
화면은 캐릭터의 판(asset 서버)의 해금 대상 목록과 이것을 맞춰 "3/10" 과 흐린 그림을 그린다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentViewer, Paging, Session
from app.gallery import repository
from app.gallery.models import SceneUnlock
from app.gallery.schemas import UnlockOut, UnlockPage

router = APIRouter(prefix='/gallery', tags=['gallery'])


def to_unlock(row: SceneUnlock) -> UnlockOut:
    """기록 한 줄을 응답의 모양으로."""
    return UnlockOut(character_id=row.character_source, scene_id=row.scene_id, unlocked_at=row.unlocked_at)


@router.get('', response_model=UnlockPage, status_code=status.HTTP_200_OK)
async def list_unlocks(
    viewer: CurrentViewer,
    session: Session,
    paging: Paging,
    character_id: Annotated[
        uuid.UUID | None, Query(description='asset 서버의 캐릭터 id. 주면 그 캐릭터의 것만')
    ] = None,
) -> UnlockPage:
    """내가 연 이벤트 씬들. 최근에 연 것부터다."""
    rows, total = await repository.list_unlocks(
        session, viewer.claims.user_id, character_id, paging.limit, paging.offset
    )
    return UnlockPage(items=[to_unlock(row) for row in rows], total=total)
