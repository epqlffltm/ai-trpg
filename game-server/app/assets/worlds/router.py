# game-server/app/assets/worlds/router.py

"""
세계관 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

규칙은 여기 없다. 누가 보낸 요청인지(토큰)와 입력의 모양만 확인하고 서비스에 맡긴다.
모든 주소가 로그인을 요구한다. 자기 세계관만 다룰 수 있다.
"""

import uuid

from fastapi import APIRouter, status

from app.assets.models import World
from app.assets.routing import Paging, Session, to_page, to_summary
from app.assets.schemas import AssetPage
from app.assets.worlds import service
from app.assets.worlds.schemas import WorldCreate, WorldDetail, WorldUpdate
from app.auth.dependencies import CurrentUser

router = APIRouter(prefix='/worlds', tags=['worlds'])


def to_detail(world: World) -> WorldDetail:
    """세계관을 만든 사람에게 보여 주는 응답으로 바꾼다. gm_notes 까지 싣는다."""
    return WorldDetail(**to_summary(world.asset).model_dump(), setting=world.setting, gm_notes=world.gm_notes)


@router.post('', response_model=WorldDetail, status_code=status.HTTP_201_CREATED)
async def create_world(data: WorldCreate, user: CurrentUser, session: Session) -> WorldDetail:
    """세계관을 만든다. 만든 사람은 요청의 본문이 아니라 토큰에서 정해진다."""
    world = await service.create_world(session, user.user_id, data)
    return to_detail(world)


@router.get('', response_model=AssetPage, status_code=status.HTTP_200_OK)
async def list_worlds(user: CurrentUser, session: Session, paging: Paging) -> AssetPage:
    """자기 세계관의 목록을 최근에 만든 것부터 돌려준다."""
    worlds, total = await service.list_worlds(session, user.user_id, paging.limit, paging.offset)
    return to_page(worlds, total)


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
