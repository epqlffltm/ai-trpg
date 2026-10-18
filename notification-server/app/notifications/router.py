# notification-server/app/notifications/router.py

"""
다른 서버가 알림을 넣는 API. 사용자의 토큰이 아니라 그 서버의 서명으로 확인한다(app/service_auth/signing.py).

    POST /api/v1/notification/service/{source}/notifications

  - source 는 넣는 서버의 이름(game, billing, board)이다. 주소까지 서명하므로 남의 이름으로 넣을 수 없다
  - 서명이 없거나 틀렸거나, 그 서버의 비밀이 설정에 없으면 401 이다. 어느 경우인지 나누지 않는다
  - 본문은 서명을 확인한 뒤에 읽는다. 서명을 확인하기 전에는 받은 바이트를 해석하지 않는다
  - 그 서버가 넣을 수 없는 kind 이거나 payload 에 꼭 있어야 하는 칸이 없으면 422 다(app/notifications/catalog.py)
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
from app.notifications import catalog, service
from app.notifications.schemas import NotificationIn, NotificationPut, PutStatus
from app.service_auth.signing import SIGNATURE_HEADER, is_valid

logger = logging.getLogger(__name__)

# 받는 본문의 상한(바이트). 알림 하나에는 이만큼이면 넉넉하다(값은 2048바이트까지).
# 서명을 확인하려면 본문 전체를 읽어야 하므로, 서명을 확인하기 전에 크기부터 자른다
BODY_MAX_BYTES = 16 * 1024

# 넣기의 로그의 operation 과, kind 의 표에 맞지 않아 받지 않았을 때의 error_code(docs/observability.md)
PUT_OPERATION = 'notification.put'
KIND_REFUSED_ERROR_CODE = 'notification.kind_refused'

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


def refused(kind: str, refusal: catalog.Refusal) -> HTTPException:
    """kind 의 표에 맞지 않는 알림의 응답. 넣는 서버가 무엇을 고칠지 알 수 있게 까닭과 빠진 칸을 싣는다."""
    detail = {'code': refusal.code.value, 'kind': kind}
    if refusal.missing:
        detail['missing'] = list(refusal.missing)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def log_refusal(source: str, kind: str, refusal: catalog.Refusal) -> None:
    """
    받지 않은 알림을 로그에 남긴다. 받는 사람과 값은 남기지 않는다.

    넣는 서버의 버그이거나 남의 kind 를 넣으려 한 것이다. 넣는 서버도 notification.rejected 를 error 로 남긴다.
    """
    logger.warning(
        '알림의 종류가 표에 맞지 않아 받지 않았다',
        extra={
            'operation': PUT_OPERATION,
            'source': source,
            'kind': kind,
            'result': 'client_error',
            'error_code': KIND_REFUSED_ERROR_CODE,
            'refusal': refusal.code.value,
            'missing_fields': ','.join(refusal.missing),
        },
    )


def ensure_listed(source: str, incoming: NotificationIn) -> None:
    """그 서버가 그 알림을 넣어도 되는지 본다. 안 되면 로그를 남기고 422 다. DB 에 닿기 전에 본다."""
    refusal = catalog.refusal_for(source, incoming.kind, incoming.payload)
    if refusal is None:
        return
    log_refusal(source, incoming.kind, refusal)
    raise refused(incoming.kind, refusal)


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
    ensure_listed(source, incoming)
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
