# game-server/app/drafts/router.py

"""
장부 초안 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소는 테이블 아래에 둔다(/tables/{table_id}/ledger-drafts). 초안은 테이블에 딸린 것이다.
방장만 본다. 숨긴 퀘스트가 드러났다는 줄이 있을 수 있다. 다른 사람에게는 403 이다(앉아 있으니 테이블이 있는 것은 안다).
"""

import uuid

from fastapi import APIRouter, status
from pydantic import TypeAdapter

from app.assets.routing import Session
from app.auth.dependencies import CurrentUser
from app.drafts import repository
from app.drafts.models import LedgerDraft
from app.drafts.schemas import LedgerDraftList, LedgerDraftOut
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
