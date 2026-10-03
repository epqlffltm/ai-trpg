# game-server/app/assets/router.py

"""
세계관 API. 요청을 받아 서비스(service.py)에 넘기고, 결과를 응답의 모양으로 바꾼다.

규칙은 여기 없다. 누가 보낸 요청인지(토큰)와 입력의 모양만 확인하고 서비스에 맡긴다.
모든 주소가 로그인을 요구한다. 자기 세계관만 다룰 수 있다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service
from app.assets.models import World
from app.assets.schemas import WorldCreate, WorldDetail, WorldPage, WorldSummary, WorldUpdate
from app.assets.service import WorldNotFoundError
from app.auth.dependencies import CurrentUser
from app.core.database import get_session

router = APIRouter(prefix='/worlds', tags=['worlds'])

# 요청 하나가 쓰는 DB 세션
Session = Annotated[AsyncSession, Depends(get_session)]

# 목록의 한 쪽에 싣는 개수. 상한을 둔다. 한 번에 전부 달라는 요청으로 서버가 느려지지 않게 한다
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def to_summary(world: World) -> WorldSummary:
    """세계관을 목록용 응답으로 바꾼다. 긴 글은 싣지 않는다."""
    asset = world.asset
    return WorldSummary(
        id=asset.id,
        title=asset.title,
        description=asset.description,
        rating=asset.rating,
        visibility=asset.visibility,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def to_detail(world: World) -> WorldDetail:
    """세계관을 만든 사람에게 보여 주는 응답으로 바꾼다. gm_notes 까지 싣는다."""
    return WorldDetail(**to_summary(world).model_dump(), setting=world.setting, gm_notes=world.gm_notes)


async def handle_world_not_found(request: Request, error: WorldNotFoundError) -> JSONResponse:
    """
    서비스가 "그런 세계관이 없다"고 하면 404 로 답한다. 앱에 한 번 등록한다(app/main.py).

    남의 세계관도 404 다. 403 을 주면 그 ID 의 자산이 있다는 것이 드러난다.
    """
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '세계관을 찾을 수 없습니다.'})


@router.post('', response_model=WorldDetail, status_code=status.HTTP_201_CREATED)
async def create_world(data: WorldCreate, user: CurrentUser, session: Session) -> WorldDetail:
    """세계관을 만든다. 만든 사람은 요청의 본문이 아니라 토큰에서 정해진다."""
    world = await service.create_world(session, user.user_id, data)
    return to_detail(world)


@router.get('', response_model=WorldPage, status_code=status.HTTP_200_OK)
async def list_worlds(
    user: CurrentUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorldPage:
    """자기 세계관의 목록을 최근에 만든 것부터 돌려준다."""
    worlds, total = await service.list_worlds(session, user.user_id, limit, offset)
    return WorldPage(items=[to_summary(world) for world in worlds], total=total)


@router.get('/{world_id}', response_model=WorldDetail, status_code=status.HTTP_200_OK)
async def read_world(world_id: uuid.UUID, user: CurrentUser, session: Session) -> WorldDetail:
    """자기 세계관 하나를 돌려준다."""
    world = await service.get_world(session, user.user_id, world_id)
    return to_detail(world)


@router.patch('/{world_id}', response_model=WorldDetail, status_code=status.HTTP_200_OK)
async def update_world(world_id: uuid.UUID, data: WorldUpdate, user: CurrentUser, session: Session) -> WorldDetail:
    """자기 세계관을 고친다. 보낸 칸만 바뀐다."""
    world = await service.update_world(session, user.user_id, world_id, data)
    return to_detail(world)


@router.delete('/{world_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_world(world_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 세계관을 지운다."""
    await service.delete_world(session, user.user_id, world_id)
