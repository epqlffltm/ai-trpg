# story-server/app/operators/router.py

"""
운영자 API(chat 의 #678 과 같다). 세션 속 답의 신고를 보고 처리한다.

주소는 /admin 아래에 따로 묶는다(docs/architecture/operators.md).
  - 운영자(토큰의 roles 에 "operator")가 아니면 404 다. 운영자의 주소가 있다는 것을 알리지 않는다
  - 신고에 굳힌 세션의 글을 보는 주소는 쿼리로, 처리하는 주소는 본문으로 사유(reason, 1~200자)를 받는다. 없으면 422 다
  - 신고의 목록은 세션의 글을 싣지 않아 사유를 받지 않는다
처리는 신고와 감사 기록에 적을 뿐 세계관을 숨기지 않는다.
asset 의 숨기기 API 는 아직 캐릭터만이다(신고에 세계관의 id 가 있다).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.core.dependencies import CurrentViewer, Paging, Session, Viewer
from app.operators import service
from app.operators.schemas import OutcomeInput, Reason, ReportDetailOut, ReportPage, ReportSummaryOut
from app.operators.service import AlreadyHandledError, ReportNotFoundError

router = APIRouter(prefix='/admin', tags=['admin'])


def require_operator(viewer: CurrentViewer) -> Viewer:
    """운영자만 통과시킨다. 아니면 404 다(403 이면 운영자의 주소가 있다는 것이 드러난다)."""
    if not viewer.claims.is_operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not Found')
    return viewer


Operator = Annotated[Viewer, Depends(require_operator)]


def utc_now() -> datetime:
    """서버의 지금 시각(UTC)."""
    return datetime.now(UTC)


async def handle_report_not_found(request: Request, error: ReportNotFoundError) -> JSONResponse:
    """그런 신고가 없으면 404 다."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.', 'code': 'report_not_found'}
    )


async def handle_already_handled(request: Request, error: AlreadyHandledError) -> JSONResponse:
    """이미 처리한 신고면 409 다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={'detail': '이미 처리한 신고입니다.', 'code': 'already_handled'}
    )


@router.get('/message-reports', response_model=ReportPage, status_code=status.HTTP_200_OK)
async def list_reports(operator: Operator, session: Session, paging: Paging) -> ReportPage:
    """열린 신고의 목록. minor 가 먼저, 그다음 오래된 것부터. 세션의 글은 싣지 않는다."""
    found, total = await service.list_open(session, paging.limit, paging.offset)
    return ReportPage(
        items=[ReportSummaryOut.model_validate(item, from_attributes=True) for item in found], total=total
    )


@router.get('/message-reports/{report_id}', response_model=ReportDetailOut, status_code=status.HTTP_200_OK)
async def read_report(
    report_id: uuid.UUID, reason: Annotated[Reason, Query()], operator: Operator, session: Session
) -> ReportDetailOut:
    """신고 하나와 굳힌 세션의 글. 볼 때마다 감사 기록에 남는다(사유가 필수다). 없으면 404 다."""
    report = await service.read_report(session, operator.claims.user_id, report_id, reason, utc_now())
    return ReportDetailOut.model_validate(report, from_attributes=True)


@router.put('/message-reports/{report_id}/outcome', status_code=status.HTTP_204_NO_CONTENT)
async def handle_report(report_id: uuid.UUID, data: OutcomeInput, operator: Operator, session: Session) -> None:
    """신고를 처리한다. 없으면 404, 이미 처리했으면 409 다."""
    await service.handle_report(session, operator.claims.user_id, report_id, data.outcome, data.reason, utc_now())
