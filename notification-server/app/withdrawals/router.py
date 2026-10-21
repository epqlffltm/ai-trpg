# notification-server/app/withdrawals/router.py

"""
인증 서버가 탈퇴를 알리는 API(#603, docs/architecture/withdrawal.md 의 "알리는 길"). 인증 서버의 서명으로 확인한다.

    POST /api/v1/notification/service/users/{user_id}/withdrawal
    본문: {"withdrawn_at": "2026-10-28T03:00:00+00:00"}
    답: 200 {"status": "processed"}

  - 서명의 비밀은 AUTH_SERVER_SECRET 이다. 알림을 넣는 서버의 비밀로는 부를 수 없다. 비어 있으면 모두 401 이다
  - 본문은 서명을 확인한 뒤에 읽는다. 모양이 틀리면 422 다
  - 인증 서버는 200 과 processed 를 받을 때까지 다시 보낸다. 그래서 몇 번을 받아도 같고,
    이미 지운 사람과 이 서버가 모르는 사람도 200 이다
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from server_core.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.signed_requests import body_signed_with
from app.withdrawals import service
from app.withdrawals.schemas import Erased, WithdrawalIn, WithdrawalOut, WithdrawalStatus

logger = logging.getLogger(__name__)

# 로그의 operation(docs/observability.md)
WITHDRAWAL_OPERATION = 'notification.withdrawal'

router = APIRouter(tags=['service'])


async def auth_signed_body(request: Request) -> bytes:
    """인증 서버의 서명을 확인하고 본문을 돌려준다. FastAPI 의 의존성으로 쓴다. 틀리면 401 이다."""
    secret = request.app.state.settings.auth_server_secret.get_secret_value()
    return await body_signed_with(request, secret)


def parse_withdrawal(body: bytes) -> WithdrawalIn:
    """서명을 확인한 본문을 탈퇴의 알림으로 읽는다. 틀리면 다른 API 와 같은 422 다."""
    try:
        return WithdrawalIn.model_validate_json(body)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error


def log_erased(erased: Erased) -> None:
    """지운 수를 로그에 남긴다. 사람(user_id)은 남기지 않는다."""
    logger.info(
        '탈퇴한 사람의 알림을 지웠다',
        extra={
            'operation': WITHDRAWAL_OPERATION,
            'deleted_notifications': erased.notifications,
            'deleted_mutes': erased.mutes,
        },
    )


@router.post(
    '/service/users/{user_id}/withdrawal',
    response_model=WithdrawalOut,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {'description': '서명이 없거나 맞지 않다(AUTH_SERVER_SECRET)'},
        status.HTTP_413_CONTENT_TOO_LARGE: {'description': '본문이 16KB 를 넘는다'},
    },
)
async def receive_withdrawal(
    user_id: uuid.UUID,
    body: Annotated[bytes, Depends(auth_signed_body)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WithdrawalOut:
    """그 사람의 알림과 끈 종류를 지운다. 지웠든, 이미 지웠든, 없던 사람이든 200 이다."""
    parse_withdrawal(body)
    erased = await service.erase_user(session, user_id)
    log_erased(erased)
    return WithdrawalOut(status=WithdrawalStatus.PROCESSED)
