# game-server/app/drafts/router.py

"""
장부 초안 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소는 테이블 아래에 둔다(/tables/{table_id}/ledger-drafts). 초안은 테이블에 딸린 것이다.
방장만 본다. 숨긴 퀘스트가 드러났다는 줄이 있을 수 있다. 다른 사람에게는 403 이다(앉아 있으니 테이블이 있는 것은 안다).
받아들이고 버리는 것도 방장만 한다(app/drafts/decisions.py).
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from app.assets.routing import Session
from app.auth.dependencies import CurrentUser
from app.drafts import decisions, repository
from app.drafts.decisions import DraftNotFoundError
from app.drafts.models import LedgerDraft
from app.drafts.schemas import LedgerDraftList, LedgerDraftOut
from app.tables.router import to_detail
from app.tables.schemas import TableDetail
from app.tables.service import get_table
from app.tables.state import require_host

router = APIRouter(prefix='/tables/{table_id}/ledger-drafts', tags=['ledger-drafts'])

# 줄 하나를 응답의 모양으로 읽는 법. kind 로 모양을 고른다
DRAFT_OUT = TypeAdapter(LedgerDraftOut)


def to_draft(draft: LedgerDraft) -> LedgerDraftOut:
    """줄 하나를 응답으로 바꾼다. 내용(payload)의 칸을 펼친다."""
    fields = {
        'id': draft.id,
        'kind': draft.kind,
        'round': draft.round_number,
        'created_at': draft.created_at,
        **draft.payload,
    }
    return DRAFT_OUT.validate_python(fields)


@router.get('', response_model=LedgerDraftList, status_code=status.HTTP_200_OK)
async def list_pending(table_id: uuid.UUID, user: CurrentUser, session: Session) -> LedgerDraftList:
    """
    방장의 결정을 기다리는 장부 초안의 줄들. 방장만 본다.

    다음 라운드의 초안이 오면 결정하지 않은 줄은 만료되어 여기서 빠진다.
    """
    table = await get_table(session, user.user_id, table_id)
    require_host(table, user.user_id)
    return LedgerDraftList(items=[to_draft(draft) for draft in await repository.list_pending(session, table.id)])


@router.post('/{draft_id}/accept', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def accept_draft(table_id: uuid.UUID, draft_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """
    방장이 줄 하나를 받아들인다. 그때의 장부로 다시 보고 바꾼다. 진행 중에만 된다.

    물건이면 items_gained, 퀘스트면 quest_changed 가 모두에게 간다(방장이 손으로 할 때와 같다).
    이미 결정했거나 만료된 줄은 409(draft_decided). 그사이 캐릭터가 바뀌었으면 409(draft_stale),
    죽었으면 409(character_dead), 이미 99 개면 409(too_many_items), 퀘스트를 바꿀 수 없으면 그 충돌이다.
    """
    table = await decisions.accept_draft(session, user.user_id, table_id, draft_id)
    return to_detail(table, user.user_id)


@router.post('/{draft_id}/reject', status_code=status.HTTP_204_NO_CONTENT)
async def reject_draft(table_id: uuid.UUID, draft_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """방장이 줄 하나를 버린다. 장부는 그대로다. 끝난 테이블에서도 된다. 이미 결정했거나 만료된 줄은 409."""
    await decisions.reject_draft(session, user.user_id, table_id, draft_id)


async def handle_draft_not_found(request: Request, error: DraftNotFoundError) -> JSONResponse:
    """ "그 테이블에 그런 줄이 없다"는 404 다. 다른 테이블의 줄도 없는 것과 같다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '장부 초안을 찾을 수 없습니다.'})
