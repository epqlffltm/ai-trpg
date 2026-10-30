# story-server/app/reports/router.py

"""
세션 속 모델의 답을 신고하는 API(chat 의 #678 과 같다).
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.dependencies import CurrentViewer, Session
from app.limits.routing import WRITE_LIMIT
from app.reports import service
from app.reports.schemas import ReportCreate, ReportCreated
from app.reports.service import AlreadyReportedError, NotReportableError

router = APIRouter(prefix='/messages', tags=['messages'])


async def handle_not_reportable(request: Request, error: NotReportableError) -> JSONResponse:
    """사람의 말이나 행동 말을 신고하면 422 다. 화면은 모델의 답에만 신고를 보인다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '모델의 답만 신고할 수 있습니다.', 'code': 'not_reportable'},
    )


async def handle_already_reported(request: Request, error: AlreadyReportedError) -> JSONResponse:
    """이미 신고했으면 409 다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={'detail': '이미 신고했습니다.', 'code': 'already_reported'}
    )


@router.post(
    '/{message_id}/reports',
    response_model=ReportCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WRITE_LIMIT],
)
async def report_message(
    message_id: uuid.UUID, data: ReportCreate, viewer: CurrentViewer, session: Session
) -> ReportCreated:
    """
    모델의 답을 신고한다. 그 답과 앞의 말 몇 개를 신고에 굳혀 둔다(운영자는 이것만 본다).
    없거나 남의 세션의 말이면 404, 사람의 말이나 행동 말이면 422, 이미 신고했으면 409 다.
    """
    report = await service.file_report(session, viewer, message_id, data)
    return ReportCreated(id=report.id, created_at=report.created_at)
