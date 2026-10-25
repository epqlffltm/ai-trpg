# board-server/app/withdrawal/router.py

"""
인증 서버가 탈퇴를 알리는 API(docs/architecture/withdrawal.md 의 "알리는 길"). 인증 서버만 부른다.

    POST /api/v1/board/service/users/{userId}/withdrawal   {"withdrawn_at": "..."}  ->  200 {"status": "processed"}

  - 사용자의 토큰이 아니라 인증 서버의 서명을 본다(app/core/service_auth.py). 로그인은 보지 않는다
  - 인증 서버는 200 과 processed 를 받을 때까지 다시 보낸다. 몇 번을 받아도 같고, 모르는 사람이어도 200 이다
  - 서명이 틀리면 401, 주소의 번호나 본문이 틀리면 400 이다. 둘 다 인증 서버는 다시 보낸다(코드의 버그다)
  - 검사의 차례는 NestJS 로 쓰던 때와 같다: 서명(401) -> 주소의 번호(400, 칸을 가르지 않는다) -> 본문(400)
"""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import Session
from app.core.errors import ApiError
from app.core.service_auth import SIGNATURE_PARAMETER, verify_auth_server
from app.withdrawal import service
from app.withdrawal.schemas import WITHDRAWAL_PROCESSED, WithdrawalDto, WithdrawalResponse

# NestJS 의 ParseUUIDPipe 가 받던 모양. 하이픈이 있는 36자이고 판(version)은 보지 않는다
UUID_PATTERN = re.compile(r'^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\Z', re.IGNORECASE | re.ASCII)

# 주소의 번호가 틀렸을 때의 문장. 그때처럼 칸을 가르지 않는 기본 문장이다
BAD_USER_ID_DETAIL = '요청이 올바르지 않습니다.'

router = APIRouter(prefix='/service/users', tags=['Withdrawals'], dependencies=[Depends(verify_auth_server)])


def withdrawn_user_id(user_id: Annotated[str, Path(alias='userId')]) -> uuid.UUID:
    """주소의 사용자 번호. UUID 가 아니면 400 이다. 본문보다 먼저 본다."""
    if UUID_PATTERN.match(user_id) is None:
        raise ApiError(status.HTTP_400_BAD_REQUEST, BAD_USER_ID_DETAIL)
    return uuid.UUID(user_id)


@router.post(
    '/{userId}/withdrawal',
    response_model=WithdrawalResponse,
    status_code=status.HTTP_200_OK,
    openapi_extra={'parameters': [SIGNATURE_PARAMETER], 'x-audience': 'service'},
)
async def receive(
    user_id: Annotated[uuid.UUID, Depends(withdrawn_user_id)],
    # 본문은 검사만 한다. 지우는 일은 이 값을 쓰지 않는다
    withdrawal: WithdrawalDto,
    session: Session,
) -> WithdrawalResponse:
    """그 사람의 글과 댓글의 글쓴이, 신고한 사람을 비우고 닉네임과 보낼 알림을 지운다."""
    service.log_erased(await service.erase(session, user_id))
    return WithdrawalResponse(status=WITHDRAWAL_PROCESSED)
