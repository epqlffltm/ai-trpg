# asset-server/app/reports/router.py

"""
공개 캐릭터를 신고하는 API(#678). 로그인한 사람만 쓴다.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser

from app.core.dependencies import Session
from app.reports import service
from app.reports.schemas import ReportCreate, ReportCreated
from app.reports.service import AlreadyReportedError, OwnCharacterReportError

router = APIRouter(prefix='/listings/characters', tags=['listings'])


async def handle_own_character(request: Request, error: OwnCharacterReportError) -> JSONResponse:
    """자기 캐릭터를 신고하면 403 이다. 화면은 자기 캐릭터에 신고 버튼을 보이지 않는다."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={'detail': '자기 캐릭터는 신고할 수 없습니다.', 'code': 'own_character'},
    )


async def handle_already_reported(request: Request, error: AlreadyReportedError) -> JSONResponse:
    """이미 신고했으면 409 다. 화면은 "이미 신고했습니다"를 보인다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={'detail': '이미 신고했습니다.', 'code': 'already_reported'}
    )


@router.post('/{character_id}/reports', response_model=ReportCreated, status_code=status.HTTP_201_CREATED)
async def report_character(
    character_id: uuid.UUID, data: ReportCreate, user: CurrentUser, session: Session
) -> ReportCreated:
    """공개 캐릭터를 신고한다. 볼 수 없는 캐릭터는 404, 자기 것은 403, 이미 신고했으면 409 다."""
    report = await service.file_report(session, user, character_id, data)
    return ReportCreated(id=report.id, created_at=report.created_at)
