# asset-server/app/operators/router.py

"""
운영자 API(#678). 신고를 보고 캐릭터를 숨기고 푼다. 세계관도 숨기고 푼다(story 의 신고를 보고).

주소는 /admin 아래에 따로 묶는다. 일반 사용자의 API 에 섞지 않는다(docs/architecture/operators.md).
  - 운영자(토큰의 roles 에 "operator")가 아니면 404 다. 운영자의 주소가 있다는 것을 알리지 않는다
  - 조치하는 주소는 본문에 사유(reason, 1~200자)를 받는다. 없으면 422 다. 조치마다 감사 기록에 남는다
  - 신고의 목록과 한 캐릭터의 신고는 사유를 받지 않는다. 운영자에게 보낸 것이고 남의 비공개 내용이 아니다
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from server_core.auth.dependencies import CurrentUser
from server_core.auth.tokens import AccessClaims

from app.core.dependencies import Paging, Session
from app.operators import service
from app.operators.schemas import (
    HiddenInput,
    HiddenResult,
    OpenReportGroupOut,
    OpenReportPage,
    OutcomeInput,
    OutcomeResult,
    ReportOut,
)

router = APIRouter(prefix='/admin', tags=['admin'])


def require_operator(user: CurrentUser) -> AccessClaims:
    """운영자만 통과시킨다. 아니면 404 다(403 이면 운영자의 주소가 있다는 것이 드러난다)."""
    if not user.is_operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not Found')
    return user


Operator = Annotated[AccessClaims, Depends(require_operator)]


def utc_now() -> datetime:
    """서버의 지금 시각(UTC)."""
    return datetime.now(UTC)


@router.get('/character-reports', response_model=OpenReportPage, status_code=status.HTTP_200_OK)
async def list_open_reports(operator: Operator, session: Session, paging: Paging) -> OpenReportPage:
    """열린 신고를 캐릭터마다 묶은 목록. minor 가 있는 것이 먼저, 그다음 마지막 신고가 최근인 것부터다."""
    groups, total = await service.list_open(session, paging.limit, paging.offset)
    return OpenReportPage(items=[OpenReportGroupOut(**vars(group)) for group in groups], total=total)


@router.get('/characters/{character_id}/reports', response_model=list[ReportOut], status_code=status.HTTP_200_OK)
async def list_character_reports(character_id: uuid.UUID, operator: Operator, session: Session) -> list[ReportOut]:
    """그 캐릭터의 신고 전부(처리된 것까지). 최근 것부터. 캐릭터가 없으면 404 다."""
    found = await service.list_reports(session, character_id)
    return [ReportOut.model_validate(report, from_attributes=True) for report in found]


@router.put('/characters/{character_id}/reports/outcome', response_model=OutcomeResult, status_code=status.HTTP_200_OK)
async def handle_reports(
    character_id: uuid.UUID, data: OutcomeInput, operator: Operator, session: Session
) -> OutcomeResult:
    """그 캐릭터의 열린 신고를 처리한다. actioned 면 숨기고, dismissed 면 그대로 둔다. 캐릭터가 없으면 404 다."""
    handled, hidden = await service.handle_reports(
        session, operator.user_id, character_id, data.outcome, data.reason, utc_now()
    )
    return OutcomeResult(handled=handled, hidden=hidden)


@router.put('/characters/{character_id}/hidden', response_model=HiddenResult, status_code=status.HTTP_200_OK)
async def change_hidden(
    character_id: uuid.UUID, data: HiddenInput, operator: Operator, session: Session
) -> HiddenResult:
    """캐릭터를 숨기거나 푼다. 캐릭터가 없으면 404 다."""
    hidden = await service.change_hidden(session, operator.user_id, character_id, data.hidden, data.reason, utc_now())
    return HiddenResult(hidden=hidden)


@router.put('/worlds/{world_id}/hidden', response_model=HiddenResult, status_code=status.HTTP_200_OK)
async def change_world_hidden(
    world_id: uuid.UUID, data: HiddenInput, operator: Operator, session: Session
) -> HiddenResult:
    """세계관을 숨기거나 푼다. 세계관이 없으면 404 다. story 의 신고(world_id)를 보고 한다."""
    hidden = await service.change_world_hidden(session, operator.user_id, world_id, data.hidden, data.reason, utc_now())
    return HiddenResult(hidden=hidden)
