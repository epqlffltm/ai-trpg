# notification-server/app/notifications/router.py

"""
다른 서버가 알림을 넣는 API. 사용자의 토큰이 아니라 그 서버의 서명으로 확인한다(app/service_auth/signing.py).

    POST /api/v1/notification/service/{source}/notifications

  - source 는 넣는 서버의 이름(game, billing, board)이다. 주소까지 서명하므로 남의 이름으로 넣을 수 없다
  - 서명이 없거나 틀렸거나, 그 서버의 비밀이 설정에 없으면 401 이다. 어느 경우인지 나누지 않는다
  - 본문은 서명을 확인한 뒤에 읽는다. 서명을 확인하기 전에는 받은 바이트를 해석하지 않는다
  - 새로 넣었으면 201, 같은 알림을 다시 보냈으면 200(같은 id), 같은 열쇠의 다른 알림이면 409 다
"""

import logging
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.notifications import service
from app.notifications.schemas import NotificationIn, NotificationPut, PutStatus
from app.service_auth.signing import SIGNATURE_HEADER, is_valid

logger = logging.getLogger(__name__)

# 받는 본문의 상한(바이트). 알림 하나에는 이만큼이면 넉넉하다(값은 2048바이트까지).
# 서명을 확인하려면 본문 전체를 읽어야 하므로, 서명을 확인하기 전에 크기부터 자른다
BODY_MAX_BYTES = 16 * 1024

# 넣기의 로그의 operation(docs/observability.md)
PUT_OPERATION = 'notification.put'

router = APIRouter(tags=['service'])


def unauthorized() -> HTTPException:
    """서명을 받아들일 수 없을 때의 응답. 이유를 싣지 않는다. 무엇이 틀렸는지 알려 주면 꾸며 내는 쪽에 도움이 된다."""
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='요청의 서명이 맞지 않습니다.')


def signed_path(request: Request) -> str:
    """서명하는 주소. 호스트를 뺀 경로와, 있으면 쿼리다."""
    query = request.url.query
    return f'{request.url.path}?{query}' if query else request.url.path


async def read_body(request: Request) -> bytes:
    """본문을 읽는다. 상한을 넘으면 413 이다. 서명을 확인하기 전에 큰 본문을 끝까지 읽지 않는다."""
    declared = request.headers.get('content-length')
    if declared is not None and declared.isdigit() and int(declared) > BODY_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail='본문이 너무 큽니다.')
    body = b''
    async for chunk in request.stream():
        body += chunk
        if len(body) > BODY_MAX_BYTES:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail='본문이 너무 큽니다.')
    return body


async def verified_body(request: Request, source: Annotated[str, Path(pattern=r'^[a-z][a-z0-9_-]{0,31}$')]) -> bytes:
    """
    넣는 서버의 서명을 확인하고 본문을 돌려준다. FastAPI 의 의존성으로 쓴다.

    모르는 서버이거나 그 서버의 비밀이 비어 있으면 401 이다. 404 로 나누지 않는다(어느 이름이 있는지 알리지 않는다).
    """
    body = await read_body(request)
    secret = request.app.state.settings.service_secrets().get(source, '')
    header = request.headers.get(SIGNATURE_HEADER)
    if not is_valid(secret, header, request.method, signed_path(request), body, time.time()):
        raise unauthorized()
    return body


def parse_notification(body: bytes) -> NotificationIn:
    """서명을 확인한 본문을 알림으로 읽는다. 틀리면 다른 API 와 같은 422 다."""
    try:
        return NotificationIn.model_validate_json(body)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error


@router.post(
    '/service/{source}/notifications',
    response_model=NotificationPut,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {'model': NotificationPut, 'description': '같은 알림을 다시 보냈다'},
        status.HTTP_401_UNAUTHORIZED: {'description': '서명이 없거나 맞지 않다'},
        status.HTTP_409_CONFLICT: {'description': '같은 열쇠의 다른 알림이다'},
        status.HTTP_413_CONTENT_TOO_LARGE: {'description': '본문이 16KB 를 넘는다'},
    },
)
async def put_notification(
    source: str,
    response: Response,
    body: Annotated[bytes, Depends(verified_body)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationPut:
    """알림 하나를 넣는다. 같은 알림을 다시 보내면 같은 id 로 200 이다."""
    incoming = parse_notification(body)
    try:
        result = await service.put_notification(session, source, incoming, datetime.now(UTC))
    except service.KeyReusedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={'code': 'key_reused', 'source_key': incoming.source_key}
        ) from error
    if result.status is PutStatus.EXISTING:
        response.status_code = status.HTTP_200_OK
    # 받는 사람과 값은 남기지 않는다. 무엇이 들어왔는지만 남긴다
    logger.info(
        '알림을 넣었다',
        extra={
            'operation': PUT_OPERATION,
            'source': source,
            'kind': incoming.kind,
            'notification_id': result.id,
            'outcome': result.status.value,
        },
    )
    return result
