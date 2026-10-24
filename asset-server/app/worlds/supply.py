# asset-server/app/worlds/supply.py

"""
게시한 세계관의 판을 story 서버에 내주는 주소(#591).
그 서버의 서명(app/core/service_auth.py)과 사용자의 토큰을 함께 본다.

    GET /api/v1/asset/service/{caller}/worlds/{id}/latest           마지막 판(번호와 문서)
    GET /api/v1/asset/service/{caller}/worlds/{id}/latest/number    마지막 판의 번호만

캐릭터의 판을 내주는 길(app/characters/supply.py)과 같은 규칙이다.
  - 서명이 틀리면 401 이다. 토큰보다 먼저 본다(라우터의 의존성). story 서버는 STORY_SERVER_SECRET 으로 서명한다
  - 쓸 수 있는 사람인지는 asset-server 가 판단한다(app/worlds/service.py 의 get_usable_latest).
    주인이거나, 공개이고 그 판의 등급을 볼 수 있는 사람이다. 아니면 404 다.
    주인인데 등급을 쓸 수 없으면 403 adult_content_required 다
  - 판은 바뀌지 않는다. story 는 세션을 시작할 때 판 하나를 복사해 고정한다
"""

import uuid

from fastapi import APIRouter, Depends, status
from server_core.auth.dependencies import CurrentUser

from app.core.dependencies import Session
from app.core.service_auth import verify_caller
from app.worlds import service
from app.worlds.documents import WorldDocument
from app.worlds.schemas import WorldCopy, WorldVersionNumber

router = APIRouter(prefix='/service/{caller}/worlds', tags=['service'], dependencies=[Depends(verify_caller)])


@router.get('/{world_id}/latest', response_model=WorldCopy, status_code=status.HTTP_200_OK)
async def copy_latest(world_id: uuid.UUID, user: CurrentUser, session: Session) -> WorldCopy:
    """토큰의 주인이 쓸 수 있는 세계관의 마지막 판."""
    world, version = await service.get_usable_latest(session, user, world_id)
    return WorldCopy(
        id=world.id,
        version=version.number,
        rating=version.rating,
        published_at=version.created_at,
        document=WorldDocument.model_validate(version.document),
    )


@router.get('/{world_id}/latest/number', response_model=WorldVersionNumber, status_code=status.HTTP_200_OK)
async def read_latest_number(world_id: uuid.UUID, user: CurrentUser, session: Session) -> WorldVersionNumber:
    """토큰의 주인이 쓸 수 있는 세계관의 마지막 판의 번호."""
    world, version = await service.get_usable_latest(session, user, world_id)
    return WorldVersionNumber(id=world.id, version=version.number)
