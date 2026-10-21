# asset-server/app/withdrawal/router.py

"""
인증 서버가 탈퇴를 알리는 주소(docs/architecture/withdrawal.md 의 "알리는 길").

    POST /api/v1/asset/service/users/{public_id}/withdrawal
    본문: {"withdrawn_at": "2026-10-28T03:00:00Z"}
    서명: 인증 서버의 비밀(AUTH_SERVER_SECRET, app/core/service_auth.py)

  - 서명이 틀리면 401 이다. 본문은 서명을 확인한 뒤에 읽는다. 모양이 틀리면 422 다
  - 지우고 200 {"status": "processed"} 다. 이미 지웠거나 이 서버에 그 사람의 것이 없어도 200 이다
  - 그 밖의 답(500 등)이면 인증 서버가 간격을 늘려 다시 보낸다. 지우기가 한 트랜잭션이라 다시 와도 된다
  - 사용자의 토큰은 없다. 탈퇴한 사람에게는 토큰이 없다
  - 따로 로그를 남기지 않는다. 요청의 줄(http.request)에 경로의 틀과 결과가 남는다. 공개 ID 는 남기지 않는다
"""

import uuid

from fastapi import APIRouter, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.dependencies import Session
from app.core.service_auth import AuthServerBody
from app.withdrawal import service
from app.withdrawal.schemas import WithdrawalNotice, WithdrawalResult

router = APIRouter(prefix='/service/users', tags=['service'])


def parse_notice(body: bytes) -> WithdrawalNotice:
    """서명을 확인한 본문을 알림으로 읽는다. 틀리면 다른 API 와 같은 422 다."""
    try:
        return WithdrawalNotice.model_validate_json(body)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error


@router.post('/{public_id}/withdrawal', response_model=WithdrawalResult, status_code=status.HTTP_200_OK)
async def receive_withdrawal(public_id: uuid.UUID, body: AuthServerBody, session: Session) -> WithdrawalResult:
    """탈퇴한 사람의 페르소나와 비공개 캐릭터를 지운다."""
    parse_notice(body)
    await service.erase_user(session, public_id)
    return WithdrawalResult()
