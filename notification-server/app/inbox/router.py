# notification-server/app/inbox/router.py

"""
사용자가 자기 알림함을 읽는 API. 인증 서버가 발급한 access 토큰으로 누구인지 안다(server_core/auth).

    GET  /api/v1/notification/me/notifications                 알림함의 한 쪽(최근 것부터, ?before=&limit=)
    GET  /api/v1/notification/me/notifications/unread-count    읽지 않은 알림의 수
    POST /api/v1/notification/me/notifications/{id}/read       알림 하나를 읽음으로
    POST /api/v1/notification/me/notifications/read-all        번호 up_to 까지 모두 읽음으로

  - 누구의 알림함인지는 토큰에서만 정한다. 주소나 쿼리로 사용자 번호를 받지 않는다. 남의 알림함을 부를 길이 없다
  - 남의 알림 번호를 대면 404 다. 없는 것과 나누지 않는다
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from server_core.auth.dependencies import CurrentUser
from server_core.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from app.inbox import service
from app.inbox.schemas import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    NotificationPage,
    NotificationView,
    ReadAllRequest,
    ReadAllResult,
    UnreadCount,
)

router = APIRouter(prefix='/me/notifications', tags=['inbox'])

Session = Annotated[AsyncSession, Depends(get_session)]


def not_found() -> HTTPException:
    """그런 알림이 없거나 남의 것일 때의 응답."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='알림을 찾을 수 없습니다.')


@router.get('', response_model=NotificationPage, status_code=status.HTTP_200_OK)
async def list_notifications(
    user: CurrentUser,
    session: Session,
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
) -> NotificationPage:
    """내 알림을 최근 것부터 읽는다. 다음 쪽은 받은 next_before 를 before 로 넘긴다."""
    return await service.read_page(session, user.user_id, before, limit)


@router.get('/unread-count', response_model=UnreadCount, status_code=status.HTTP_200_OK)
async def count_unread(user: CurrentUser, session: Session) -> UnreadCount:
    """읽지 않은 알림의 수. 화면의 종 모양 옆 숫자다."""
    return await service.read_unread_count(session, user.user_id)


@router.post(
    '/{notification_id}/read',
    response_model=NotificationView,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_404_NOT_FOUND: {'description': '그런 알림이 없거나 남의 것이다'}},
)
async def read_one(user: CurrentUser, session: Session, notification_id: int) -> NotificationView:
    """알림 하나를 읽음으로 한다. 이미 읽었으면 처음 읽은 시각 그대로 200 이다."""
    try:
        return await service.mark_read(session, user.user_id, notification_id, datetime.now(UTC))
    except service.NotificationNotFoundError as error:
        raise not_found() from error


@router.post('/read-all', response_model=ReadAllResult, status_code=status.HTTP_200_OK)
async def read_all(user: CurrentUser, session: Session, request: ReadAllRequest) -> ReadAllResult:
    """번호 up_to 까지의 읽지 않은 알림을 모두 읽음으로 한다. 이번에 읽음이 된 수를 돌려준다."""
    return await service.mark_all_read(session, user.user_id, request.up_to, datetime.now(UTC))
