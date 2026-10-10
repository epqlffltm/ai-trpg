# game-server/app/assets/lorebooks/router.py

"""
로어북 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소가 두 층이다. /lorebooks 는 로어북, /lorebooks/{id}/entries 는 그 로어북의 항목이다.
항목의 주소에 로어북의 ID 가 들어 있어서, 항목은 언제나 "어느 로어북의 것인가"와 함께 다뤄진다.
모든 주소가 로그인을 요구한다. 자기 로어북만 다룰 수 있다.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.assets.lorebooks import service
from app.assets.lorebooks.schemas import EntryCreate, EntryDetail, EntryUpdate, LorebookCreate, LorebookUpdate
from app.assets.lorebooks.service import LorebookFullError
from app.assets.models import LOREBOOK_MAX_ENTRIES, LoreEntry, LoreKind
from app.assets.routing import Paging, Session, to_page, to_summary
from app.assets.schemas import AssetPage, AssetSummary
from app.auth.dependencies import CurrentUser

router = APIRouter(prefix='/lorebooks', tags=['lorebooks'])


def to_entry_detail(entry: LoreEntry) -> EntryDetail:
    """항목을 응답의 모양으로 바꾼다."""
    return EntryDetail(
        id=entry.id,
        name=entry.name,
        keywords=entry.keywords,
        content=entry.content,
        kind=LoreKind(entry.kind),
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


async def handle_lorebook_full(request: Request, error: LorebookFullError) -> JSONResponse:
    """서비스가 "로어북이 가득 찼다"고 하면 409 로 답한다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': f'로어북 하나에 항목은 {LOREBOOK_MAX_ENTRIES}개까지 넣을 수 있습니다.'},
    )


# --- 로어북 ---


@router.post('', response_model=AssetSummary, status_code=status.HTTP_201_CREATED)
async def create_lorebook(data: LorebookCreate, user: CurrentUser, session: Session) -> AssetSummary:
    """로어북을 만든다. 항목은 만든 뒤에 하나씩 더한다."""
    lorebook = await service.create_lorebook(session, user.user_id, data)
    return to_summary(lorebook.asset)


@router.get('', response_model=AssetPage, status_code=status.HTTP_200_OK)
async def list_lorebooks(user: CurrentUser, session: Session, paging: Paging) -> AssetPage:
    """자기 로어북의 목록을 최근에 만든 것부터 돌려준다."""
    lorebooks, total = await service.list_lorebooks(session, user.user_id, paging.limit, paging.offset)
    return to_page(lorebooks, total)


@router.get('/{lorebook_id}', response_model=AssetSummary, status_code=status.HTTP_200_OK)
async def read_lorebook(lorebook_id: uuid.UUID, user: CurrentUser, session: Session) -> AssetSummary:
    """자기 로어북 하나를 돌려준다. 항목은 싣지 않는다. 항목은 항목의 주소에서 읽는다."""
    lorebook = await service.get_lorebook(session, user.user_id, lorebook_id)
    return to_summary(lorebook.asset)


@router.patch('/{lorebook_id}', response_model=AssetSummary, status_code=status.HTTP_200_OK)
async def update_lorebook(
    lorebook_id: uuid.UUID, data: LorebookUpdate, user: CurrentUser, session: Session
) -> AssetSummary:
    """자기 로어북을 고친다. 보낸 칸만 바뀐다."""
    lorebook = await service.update_lorebook(session, user.user_id, lorebook_id, data)
    return to_summary(lorebook.asset)


@router.delete('/{lorebook_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_lorebook(lorebook_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 로어북을 지운다."""
    await service.delete_lorebook(session, user.user_id, lorebook_id)


# --- 항목 ---


@router.post('/{lorebook_id}/entries', response_model=EntryDetail, status_code=status.HTTP_201_CREATED)
async def add_entry(lorebook_id: uuid.UUID, data: EntryCreate, user: CurrentUser, session: Session) -> EntryDetail:
    """자기 로어북에 항목을 더한다."""
    entry = await service.add_entry(session, user.user_id, lorebook_id, data)
    return to_entry_detail(entry)


@router.get('/{lorebook_id}/entries', response_model=list[EntryDetail], status_code=status.HTTP_200_OK)
async def list_entries(lorebook_id: uuid.UUID, user: CurrentUser, session: Session) -> list[EntryDetail]:
    """자기 로어북의 항목을 만든 순서대로 전부 돌려준다."""
    entries = await service.list_entries(session, user.user_id, lorebook_id)
    return [to_entry_detail(entry) for entry in entries]


@router.patch('/{lorebook_id}/entries/{entry_id}', response_model=EntryDetail, status_code=status.HTTP_200_OK)
async def update_entry(
    lorebook_id: uuid.UUID, entry_id: uuid.UUID, data: EntryUpdate, user: CurrentUser, session: Session
) -> EntryDetail:
    """자기 로어북의 항목을 고친다. 보낸 칸만 바뀐다."""
    entry = await service.update_entry(session, user.user_id, lorebook_id, entry_id, data)
    return to_entry_detail(entry)


@router.delete('/{lorebook_id}/entries/{entry_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(lorebook_id: uuid.UUID, entry_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 로어북의 항목을 지운다."""
    await service.delete_entry(session, user.user_id, lorebook_id, entry_id)
