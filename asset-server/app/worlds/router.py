# asset-server/app/worlds/router.py

"""
story 의 세계관의 초안과 판을 다루는 API(#591, 화면 명세 D7). 만든 사람만 쓴다. 남의 것은 404 다.

/worlds 는 초안, /worlds/{id}/versions 는 그 판이다. 모양은 캐릭터의 API(app/characters/router.py)와 같다.
게시해 보기와 게시는 막는 것(problems) 말고도 알리는 것(warnings)을 싣는다.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser

from app.characters.router import to_removed
from app.core.dependencies import AppSettings, Paging, Session
from app.worlds import service
from app.worlds.models import World, WorldVersion
from app.worlds.publishing import WorldNotReadyError
from app.worlds.schemas import (
    WorldCreate,
    WorldDetail,
    WorldPage,
    WorldPublishCheck,
    WorldPublishResult,
    WorldSummary,
    WorldUpdate,
    WorldVersionCreate,
    WorldVersionDetail,
    WorldVersionSummary,
)
from app.worlds.service import CharacterNotOwnedError, WorldNotFoundError

router = APIRouter(prefix='/worlds', tags=['worlds'])


def to_detail(world: World) -> WorldDetail:
    """초안을 응답의 모양으로."""
    return WorldDetail.model_validate(world, from_attributes=True)


def to_summary(world: World) -> WorldSummary:
    """초안을 목록의 한 줄로."""
    return WorldSummary.model_validate(world, from_attributes=True)


def to_version(version: WorldVersion) -> WorldVersionDetail:
    """판을 응답의 모양으로(문서까지)."""
    return WorldVersionDetail.model_validate(version, from_attributes=True)


async def handle_world_not_found(request: Request, error: WorldNotFoundError) -> JSONResponse:
    """그런 세계관이나 판이 없으면 404 다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.'})


async def handle_character_not_owned(request: Request, error: CharacterNotOwnedError) -> JSONResponse:
    """인물이 가리키려는 캐릭터가 자기 것이 아니면(또는 없으면) 422 다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '자기 캐릭터만 인물로 넣을 수 있습니다.', 'code': 'character_not_owned'},
    )


async def handle_world_not_ready(request: Request, error: WorldNotReadyError) -> JSONResponse:
    """게시할 조건을 갖추지 못했으면 409 다. 갖추지 못한 것을 전부 싣는다(캐릭터의 게시와 같은 모양)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '게시할 조건을 갖추지 못했습니다.', 'problems': [str(item) for item in error.problems]},
    )


@router.post('', response_model=WorldDetail, status_code=status.HTTP_201_CREATED)
async def create_world(data: WorldCreate, user: CurrentUser, session: Session, settings: AppSettings) -> WorldDetail:
    """세계관을 만든다. 처음에는 비공개다. 1~2단계에는 운영자만 만든다(403 operator_only)."""
    return to_detail(await service.create_world(session, user, data, settings.characters_for_everyone))


@router.get('', response_model=WorldPage, status_code=status.HTTP_200_OK)
async def list_worlds(user: CurrentUser, session: Session, paging: Paging) -> WorldPage:
    """자기 세계관의 목록. 최근에 고친 것부터다."""
    worlds, total = await service.list_mine(session, user.user_id, paging.limit, paging.offset)
    return WorldPage(items=[to_summary(world) for world in worlds], total=total)


@router.get('/{world_id}', response_model=WorldDetail, status_code=status.HTTP_200_OK)
async def read_world(world_id: uuid.UUID, user: CurrentUser, session: Session) -> WorldDetail:
    """자기 세계관의 초안 하나."""
    return to_detail(await service.get_mine(session, user.user_id, world_id))


@router.patch('/{world_id}', response_model=WorldDetail, status_code=status.HTTP_200_OK)
async def update_world(
    world_id: uuid.UUID, data: WorldUpdate, user: CurrentUser, session: Session, settings: AppSettings
) -> WorldDetail:
    """자기 세계관의 초안을 고친다. 보낸 칸만 바뀐다. 공개로 두는 것은 운영자만이다(PUBLIC_FOR_EVERYONE 이면 누구나)."""
    return to_detail(await service.update_world(session, user, world_id, data, settings.public_for_everyone))


@router.delete('/{world_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_world(world_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 세계관을 지운다. 판도 함께 지워진다."""
    await service.delete_world(session, user.user_id, world_id)


@router.get('/{world_id}/publish-check', response_model=WorldPublishCheck, status_code=status.HTTP_200_OK)
async def check_publish(world_id: uuid.UUID, user: CurrentUser, session: Session) -> WorldPublishCheck:
    """게시해 보기. 막히는 이유, 알리는 것, 소개에서 걸러질 것을 본다. 판은 생기지 않는다."""
    problems, warnings, removed = await service.check_publish(session, user.user_id, world_id)
    return WorldPublishCheck(ready=not problems, problems=problems, warnings=warnings, removed=to_removed(removed))


@router.post('/{world_id}/versions', response_model=WorldPublishResult, status_code=status.HTTP_201_CREATED)
async def publish(
    world_id: uuid.UUID, data: WorldVersionCreate, user: CurrentUser, session: Session
) -> WorldPublishResult:
    """게시한다. 새 판과 소개에서 걸러 낸 것들, 알리는 것들을 돌려준다. 막는 것이 있으면 409 다."""
    version, removed, warnings = await service.publish(session, user.user_id, world_id, data.note)
    return WorldPublishResult(**to_version(version).model_dump(), removed=to_removed(removed), warnings=warnings)


@router.get('/{world_id}/versions', response_model=list[WorldVersionSummary], status_code=status.HTTP_200_OK)
async def list_versions(world_id: uuid.UUID, user: CurrentUser, session: Session) -> list[WorldVersionSummary]:
    """자기 세계관의 판들. 최근 것부터다."""
    versions = await service.list_versions(session, user.user_id, world_id)
    return [WorldVersionSummary.model_validate(version, from_attributes=True) for version in versions]


@router.get('/{world_id}/versions/{number}', response_model=WorldVersionDetail, status_code=status.HTTP_200_OK)
async def read_version(world_id: uuid.UUID, number: int, user: CurrentUser, session: Session) -> WorldVersionDetail:
    """자기 세계관의 판 하나. 굳힌 문서까지다."""
    return to_version(await service.get_version(session, user.user_id, world_id, number))
