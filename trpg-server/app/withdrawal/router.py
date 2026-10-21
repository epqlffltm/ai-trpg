# trpg-server/app/withdrawal/router.py

"""
인증 서버가 탈퇴를 알리는 주소(docs/architecture/withdrawal.md 의 "알리는 길").

    POST /api/v1/game/service/users/{public_id}/withdrawal
    본문: {"withdrawn_at": "2026-10-28T03:00:00Z"}
    서명: 인증 서버의 비밀(AUTH_SERVER_SECRET, app/core/service_auth.py)

  - 서명이 틀리면 401 이다. 본문은 서명을 확인한 뒤에 읽는다. 모양이 틀리면 422 다
  - 정리하고 200 {"status": "processed"} 다. 이미 정리했거나 이 서버에 그 사람의 것이 없어도 200 이다
  - 그 밖의 답(500 등)이면 인증 서버가 간격을 늘려 다시 보낸다. 다시 하면 남은 것만 한다
  - 사용자의 토큰은 없다. 탈퇴한 사람에게는 토큰이 없다
  - 프록시가 /api/v1/game/service/ 를 바깥에 열지 않는다(docker/nginx/templates/api.inc.template)
"""

import uuid

from fastapi import APIRouter, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.assets.routing import Session
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
    """탈퇴한 사람을 게임에서 정리한다."""
    parse_notice(body)
    await service.process_withdrawal(session, public_id)
    return WithdrawalResult()
