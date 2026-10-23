# asset-server/app/lorebooks/router.py

"""
로어북의 초안과 판을 다루는 API(#672). 만든 사람만 쓴다. 남의 것은 404 다.

/lorebooks 는 초안, /lorebooks/{id}/versions 는 그 판이다. 캐릭터는 초안의 lorebooks 로 로어북을 가리킨다.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser

from app.core.dependencies import AppSettings, Paging, Session
from app.lorebooks import service
from app.lorebooks.models import Lorebook, LorebookVersion
from app.lorebooks.schemas import (
    LorebookCreate,
    LorebookDetail,
    LorebookPage,
    LorebookSummary,
    LorebookUpdate,
    LorebookVersionCreate,
    LorebookVersionDetail,
    LorebookVersionSummary,
)
from app.lorebooks.service import LorebookNotFoundError

router = APIRouter(prefix='/lorebooks', tags=['lorebooks'])


def to_detail(lorebook: Lorebook) -> LorebookDetail:
    """초안을 응답의 모양으로."""
    return LorebookDetail.model_validate(lorebook, from_attributes=True)


def to_summary(lorebook: Lorebook) -> LorebookSummary:
    """초안을 목록의 한 줄로."""
    return LorebookSummary(
        id=lorebook.id,
        name=lorebook.name,
        entry_count=len(lorebook.entries),
        latest_version=lorebook.latest_version,
        updated_at=lorebook.updated_at,
    )


def to_version(version: LorebookVersion) -> LorebookVersionDetail:
    """판을 응답의 모양으로(문서까지)."""
    return LorebookVersionDetail.model_validate(version, from_attributes=True)


async def handle_lorebook_not_found(request: Request, error: LorebookNotFoundError) -> JSONResponse:
    """그런 로어북이나 판이 없으면 404 다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.', 'code': 'lorebook_not_found'}
    )


@router.post('', response_model=LorebookDetail, status_code=status.HTTP_201_CREATED)
async def create_lorebook(
    data: LorebookCreate, user: CurrentUser, session: Session, settings: AppSettings
) -> LorebookDetail:
    """로어북을 만든다. 1~2단계에는 운영자만 만든다(403 operator_only)."""
    return to_detail(await service.create_lorebook(session, user, data, settings.characters_for_everyone))


@router.get('', response_model=LorebookPage, status_code=status.HTTP_200_OK)
async def list_lorebooks(user: CurrentUser, session: Session, paging: Paging) -> LorebookPage:
    """자기 로어북의 목록. 최근에 고친 것부터다."""
    lorebooks, total = await service.list_mine(session, user.user_id, paging.limit, paging.offset)
    return LorebookPage(items=[to_summary(lorebook) for lorebook in lorebooks], total=total)


@router.get('/{lorebook_id}', response_model=LorebookDetail, status_code=status.HTTP_200_OK)
async def read_lorebook(lorebook_id: uuid.UUID, user: CurrentUser, session: Session) -> LorebookDetail:
    """자기 로어북의 초안 하나."""
    return to_detail(await service.get_mine(session, user.user_id, lorebook_id))


@router.patch('/{lorebook_id}', response_model=LorebookDetail, status_code=status.HTTP_200_OK)
async def update_lorebook(
    lorebook_id: uuid.UUID, data: LorebookUpdate, user: CurrentUser, session: Session
) -> LorebookDetail:
    """자기 로어북의 초안을 고친다. 보낸 칸만 바뀐다. 항목은 목록을 통째로 바꾼다."""
    return to_detail(await service.update_lorebook(session, user.user_id, lorebook_id, data))


@router.delete('/{lorebook_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_lorebook(lorebook_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 로어북을 지운다. 판도 함께 지워진다. 게시한 캐릭터의 판에 복사된 것은 남는다."""
    await service.delete_lorebook(session, user.user_id, lorebook_id)


@router.post('/{lorebook_id}/versions', response_model=LorebookVersionDetail, status_code=status.HTTP_201_CREATED)
async def publish(
    lorebook_id: uuid.UUID, data: LorebookVersionCreate, user: CurrentUser, session: Session
) -> LorebookVersionDetail:
    """게시한다. 새 판을 돌려준다."""
    return to_version(await service.publish(session, user.user_id, lorebook_id, data.note))


@router.get('/{lorebook_id}/versions', response_model=list[LorebookVersionSummary], status_code=status.HTTP_200_OK)
async def list_versions(lorebook_id: uuid.UUID, user: CurrentUser, session: Session) -> list[LorebookVersionSummary]:
    """자기 로어북의 판들. 최근 것부터다."""
    versions = await service.list_versions(session, user.user_id, lorebook_id)
    return [LorebookVersionSummary.model_validate(version, from_attributes=True) for version in versions]


@router.get('/{lorebook_id}/versions/{number}', response_model=LorebookVersionDetail, status_code=status.HTTP_200_OK)
async def read_version(
    lorebook_id: uuid.UUID, number: int, user: CurrentUser, session: Session
) -> LorebookVersionDetail:
    """자기 로어북의 판 하나. 굳힌 문서까지다."""
    return to_version(await service.get_version(session, user.user_id, lorebook_id, number))
