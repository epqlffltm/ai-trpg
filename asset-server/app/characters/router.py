# asset-server/app/characters/router.py

"""
캐릭터의 초안과 판을 다루는 API(#567). 만든 사람만 쓴다. 남의 것은 404 다.

/characters 는 초안, /characters/{id}/versions 는 그 판이다. 공개 목록은 따로 있다(app/characters/listings.py).
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser

from app.characters import service
from app.characters.models import Character, CharacterVersion
from app.characters.publishing import CharacterNotReadyError
from app.characters.schemas import (
    CharacterCreate,
    CharacterDetail,
    CharacterPage,
    CharacterSummary,
    CharacterUpdate,
    PublishCheck,
    PublishResult,
    RemovedItem,
    VersionCreate,
    VersionDetail,
    VersionSummary,
)
from app.characters.service import CharacterNotFoundError, LorebookNotOwnedError, OperatorOnlyError
from app.content.html import Removed
from app.core.dependencies import AppSettings, Paging, Session

router = APIRouter(prefix='/characters', tags=['characters'])


def to_detail(character: Character) -> CharacterDetail:
    """초안을 응답의 모양으로."""
    return CharacterDetail.model_validate(character, from_attributes=True)


def to_summary(character: Character) -> CharacterSummary:
    """초안을 목록의 한 줄로."""
    return CharacterSummary.model_validate(character, from_attributes=True)


def to_removed(removed: list[Removed]) -> list[RemovedItem]:
    """걸러 낸 것들을 응답의 모양으로."""
    return [RemovedItem(kind=item.kind, name=item.name) for item in removed]


def to_version(version: CharacterVersion) -> VersionDetail:
    """판을 응답의 모양으로(문서까지)."""
    return VersionDetail.model_validate(version, from_attributes=True)


async def handle_character_not_found(request: Request, error: CharacterNotFoundError) -> JSONResponse:
    """그런 캐릭터나 판이 없으면 404 다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.'})


async def handle_operator_only(request: Request, error: OperatorOnlyError) -> JSONResponse:
    """운영자만 할 수 있는 일이면 403 이다. 화면이 code 로 안내를 고른다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={'detail': '지금은 운영자만 할 수 있습니다.', 'code': 'operator_only'},
    )


async def handle_lorebook_not_owned(request: Request, error: LorebookNotOwnedError) -> JSONResponse:
    """가리키려는 로어북이 자기 것이 아니면(또는 없으면) 422 다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '자기 로어북만 가리킬 수 있습니다.', 'code': 'lorebook_not_owned'},
    )


async def handle_character_not_ready(request: Request, error: CharacterNotReadyError) -> JSONResponse:
    """게시할 조건을 갖추지 못했으면 409 다. 갖추지 못한 것을 전부 싣는다(TRPG 의 게시와 같은 모양)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '게시할 조건을 갖추지 못했습니다.', 'problems': [str(item) for item in error.problems]},
    )


@router.post('', response_model=CharacterDetail, status_code=status.HTTP_201_CREATED)
async def create_character(
    data: CharacterCreate, user: CurrentUser, session: Session, settings: AppSettings
) -> CharacterDetail:
    """캐릭터를 만든다. 처음에는 비공개다. 1~2단계에는 운영자만 만든다(403 operator_only)."""
    character = await service.create_character(session, user, data, settings.characters_for_everyone)
    return to_detail(character)


@router.get('', response_model=CharacterPage, status_code=status.HTTP_200_OK)
async def list_characters(user: CurrentUser, session: Session, paging: Paging) -> CharacterPage:
    """자기 캐릭터의 목록. 최근에 고친 것부터다."""
    characters, total = await service.list_mine(session, user.user_id, paging.limit, paging.offset)
    return CharacterPage(items=[to_summary(character) for character in characters], total=total)


@router.get('/{character_id}', response_model=CharacterDetail, status_code=status.HTTP_200_OK)
async def read_character(character_id: uuid.UUID, user: CurrentUser, session: Session) -> CharacterDetail:
    """자기 캐릭터의 초안 하나."""
    return to_detail(await service.get_mine(session, user.user_id, character_id))


@router.patch('/{character_id}', response_model=CharacterDetail, status_code=status.HTTP_200_OK)
async def update_character(
    character_id: uuid.UUID, data: CharacterUpdate, user: CurrentUser, session: Session, settings: AppSettings
) -> CharacterDetail:
    """자기 캐릭터의 초안을 고친다. 보낸 칸만 바뀐다. 공개로 두는 것은 운영자만이다(PUBLIC_FOR_EVERYONE 이면 누구나)."""
    return to_detail(await service.update_character(session, user, character_id, data, settings.public_for_everyone))


@router.delete('/{character_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_character(character_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 캐릭터를 지운다. 판도 함께 지워진다."""
    await service.delete_character(session, user.user_id, character_id)


@router.get('/{character_id}/publish-check', response_model=PublishCheck, status_code=status.HTTP_200_OK)
async def check_publish(character_id: uuid.UUID, user: CurrentUser, session: Session) -> PublishCheck:
    """게시해 보기. 막히는 이유와 소개에서 걸러질 것을 본다. 판은 생기지 않는다."""
    problems, removed = await service.check_publish(session, user.user_id, character_id)
    return PublishCheck(ready=not problems, problems=problems, removed=to_removed(removed))


@router.post('/{character_id}/versions', response_model=PublishResult, status_code=status.HTTP_201_CREATED)
async def publish(character_id: uuid.UUID, data: VersionCreate, user: CurrentUser, session: Session) -> PublishResult:
    """게시한다. 새 판과 소개에서 걸러 낸 것들을 돌려준다. 막는 것이 있으면 409 다."""
    version, removed = await service.publish(session, user.user_id, character_id, data.note)
    return PublishResult(**to_version(version).model_dump(), removed=to_removed(removed))


@router.get('/{character_id}/versions', response_model=list[VersionSummary], status_code=status.HTTP_200_OK)
async def list_versions(character_id: uuid.UUID, user: CurrentUser, session: Session) -> list[VersionSummary]:
    """자기 캐릭터의 판들. 최근 것부터다."""
    versions = await service.list_versions(session, user.user_id, character_id)
    return [VersionSummary.model_validate(version, from_attributes=True) for version in versions]


@router.get('/{character_id}/versions/{number}', response_model=VersionDetail, status_code=status.HTTP_200_OK)
async def read_version(character_id: uuid.UUID, number: int, user: CurrentUser, session: Session) -> VersionDetail:
    """자기 캐릭터의 판 하나. 굳힌 문서까지다."""
    return to_version(await service.get_version(session, user.user_id, character_id, number))
