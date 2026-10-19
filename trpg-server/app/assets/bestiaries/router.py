# trpg-server/app/assets/bestiaries/router.py

"""
몬스터 도감 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소가 두 층이다. /bestiaries 는 도감, /bestiaries/{id}/monsters 는 그 도감의 몬스터다.
몬스터의 주소에 도감의 ID 가 들어 있어서, 몬스터는 언제나 "어느 도감의 것인가"와 함께 다뤄진다.
모든 주소가 로그인을 요구한다. 자기 도감만 다룰 수 있다.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.assets.bestiaries import service
from app.assets.bestiaries.models import BESTIARY_MAX_MONSTERS, Monster, MonsterKind
from app.assets.bestiaries.schemas import BestiaryCreate, BestiaryUpdate, MonsterCreate, MonsterDetail, MonsterUpdate
from app.assets.bestiaries.service import BestiaryFullError
from app.assets.routing import Paging, Session, to_page, to_summary
from app.assets.schemas import AssetPage, AssetSummary
from app.auth.dependencies import CurrentUser

router = APIRouter(prefix='/bestiaries', tags=['bestiaries'])


def to_monster_detail(monster: Monster) -> MonsterDetail:
    """몬스터를 응답의 모양으로 바꾼다."""
    return MonsterDetail(
        id=monster.id,
        name=monster.name,
        content=monster.content,
        kind=MonsterKind(monster.kind),
        unique=monster.unique,
        created_at=monster.created_at,
        updated_at=monster.updated_at,
    )


async def handle_bestiary_full(request: Request, error: BestiaryFullError) -> JSONResponse:
    """서비스가 "도감이 가득 찼다"고 하면 409 로 답한다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': f'도감 하나에 몬스터는 {BESTIARY_MAX_MONSTERS}개까지 넣을 수 있습니다.'},
    )


# --- 도감 ---


@router.post('', response_model=AssetSummary, status_code=status.HTTP_201_CREATED)
async def create_bestiary(data: BestiaryCreate, user: CurrentUser, session: Session) -> AssetSummary:
    """도감을 만든다. 몬스터는 만든 뒤에 하나씩 더한다."""
    bestiary = await service.create_bestiary(session, user.user_id, data)
    return to_summary(bestiary.asset)


@router.get('', response_model=AssetPage, status_code=status.HTTP_200_OK)
async def list_bestiaries(user: CurrentUser, session: Session, paging: Paging) -> AssetPage:
    """자기 도감의 목록을 최근에 만든 것부터 돌려준다."""
    bestiaries, total = await service.list_bestiaries(session, user.user_id, paging.limit, paging.offset)
    return to_page(bestiaries, total)


@router.get('/{bestiary_id}', response_model=AssetSummary, status_code=status.HTTP_200_OK)
async def read_bestiary(bestiary_id: uuid.UUID, user: CurrentUser, session: Session) -> AssetSummary:
    """자기 도감 하나를 돌려준다. 몬스터는 싣지 않는다. 몬스터는 몬스터의 주소에서 읽는다."""
    bestiary = await service.get_bestiary(session, user.user_id, bestiary_id)
    return to_summary(bestiary.asset)


@router.patch('/{bestiary_id}', response_model=AssetSummary, status_code=status.HTTP_200_OK)
async def update_bestiary(
    bestiary_id: uuid.UUID, data: BestiaryUpdate, user: CurrentUser, session: Session
) -> AssetSummary:
    """자기 도감을 고친다. 보낸 칸만 바뀐다."""
    bestiary = await service.update_bestiary(session, user.user_id, bestiary_id, data)
    return to_summary(bestiary.asset)


@router.delete('/{bestiary_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_bestiary(bestiary_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 도감을 지운다."""
    await service.delete_bestiary(session, user.user_id, bestiary_id)


# --- 몬스터 ---


@router.post('/{bestiary_id}/monsters', response_model=MonsterDetail, status_code=status.HTTP_201_CREATED)
async def add_monster(
    bestiary_id: uuid.UUID, data: MonsterCreate, user: CurrentUser, session: Session
) -> MonsterDetail:
    """자기 도감에 몬스터를 더한다."""
    monster = await service.add_monster(session, user.user_id, bestiary_id, data)
    return to_monster_detail(monster)


@router.get('/{bestiary_id}/monsters', response_model=list[MonsterDetail], status_code=status.HTTP_200_OK)
async def list_monsters(bestiary_id: uuid.UUID, user: CurrentUser, session: Session) -> list[MonsterDetail]:
    """자기 도감의 몬스터를 만든 순서대로 전부 돌려준다."""
    monsters = await service.list_monsters(session, user.user_id, bestiary_id)
    return [to_monster_detail(monster) for monster in monsters]


@router.patch('/{bestiary_id}/monsters/{monster_id}', response_model=MonsterDetail, status_code=status.HTTP_200_OK)
async def update_monster(
    bestiary_id: uuid.UUID, monster_id: uuid.UUID, data: MonsterUpdate, user: CurrentUser, session: Session
) -> MonsterDetail:
    """자기 도감의 몬스터를 고친다. 보낸 칸만 바뀐다."""
    monster = await service.update_monster(session, user.user_id, bestiary_id, monster_id, data)
    return to_monster_detail(monster)


@router.delete('/{bestiary_id}/monsters/{monster_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_monster(bestiary_id: uuid.UUID, monster_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 도감의 몬스터를 지운다."""
    await service.delete_monster(session, user.user_id, bestiary_id, monster_id)
