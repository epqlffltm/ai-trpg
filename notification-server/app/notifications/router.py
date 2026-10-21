# notification-server/app/notifications/router.py

"""
다른 서버가 알림을 넣는 API. 사용자의 토큰이 아니라 그 서버의 서명으로 확인한다(server_core/service_auth/signing.py).

    POST /api/v1/notification/service/{source}/notifications

  - source 는 넣는 서버의 이름(game, billing, board)이다. 주소까지 서명하므로 남의 이름으로 넣을 수 없다
  - 서명이 없거나 틀렸거나, 그 서버의 비밀이 설정에 없으면 401 이다. 어느 경우인지 나누지 않는다
  - 본문은 서명을 확인한 뒤에 읽는다. 서명을 확인하기 전에는 받은 바이트를 해석하지 않는다
  - 그 서버가 넣을 수 없는 kind 이거나 payload 에 꼭 있어야 하는 칸이 없으면 422 다(app/notifications/catalog.py)
  - 새로 넣었으면 201, 같은 알림을 다시 보냈으면 200(같은 id), 같은 열쇠의 다른 알림이면 409 다
  - 받는 사람이 그 종류를 껐으면 적지 않고 200 이다(status: muted, id: null). 넣는 서버는 보낸 것으로 친다(#525)
  - 서명을 확인한 알림을 메트릭 notifications_received_total{source, outcome} 으로 센다.
    outcome 은 created, existing, muted, refused(422 의 kind), conflict(409) 다.
    서명이 틀린 것은 source 를 믿을 수 없어 세지 않는다(label 의 값이 끝없이 늘 수 있다)
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from server_core.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.signed_requests import body_signed_with
from app.notifications import catalog, service
from app.notifications.metrics import record_notification
from app.notifications.schemas import NotificationIn, NotificationPut, PutStatus

logger = logging.getLogger(__name__)

# 본문의 상한과 서명을 확인하는 법은 app/core/signed_requests.py 에 있다.
# 탈퇴를 받는 주소(app/withdrawals/router.py)와 함께 쓴다

# 넣기의 로그의 operation 과, kind 의 표에 맞지 않아 받지 않았을 때의 error_code(docs/observability.md)
PUT_OPERATION = 'notification.put'
KIND_REFUSED_ERROR_CODE = 'notification.kind_refused'
# 메트릭의 outcome 가운데 넣지 않은 둘. 넣은 것은 PutStatus 의 값(created, existing)이다
REFUSED_OUTCOME = 'refused'
CONFLICT_OUTCOME = 'conflict'

router = APIRouter(tags=['service'])


async def verified_body(request: Request, source: Annotated[str, Path(pattern=r'^[a-z][a-z0-9_-]{0,31}$')]) -> bytes:
    """
    넣는 서버의 서명을 확인하고 본문을 돌려준다. FastAPI 의 의존성으로 쓴다.

    모르는 서버이거나 그 서버의 비밀이 비어 있으면 401 이다. 404 로 나누지 않는다(어느 이름이 있는지 알리지 않는다).
    """
    secret = request.app.state.settings.service_secrets().get(source, '')
    return await body_signed_with(request, secret)


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
    record_notification(source, REFUSED_OUTCOME)
    raise refused(incoming.kind, refusal)


@router.post(
    '/service/{source}/notifications',
    response_model=NotificationPut,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            'model': NotificationPut,
            'description': '같은 알림을 다시 보냈다(existing). 받는 사람이 그 종류를 꺼서 적지 않았다(muted)',
        },
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
    """알림 하나를 넣는다. 같은 알림을 다시 보내면 같은 id 로 200 이다. 받는 사람이 껐으면 적지 않고 200 이다."""
    incoming = parse_notification(body)
    ensure_listed(source, incoming)
    try:
        result = await service.put_notification(session, source, incoming, datetime.now(UTC))
    except service.KeyReusedError as error:
        record_notification(source, CONFLICT_OUTCOME)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={'code': 'key_reused', 'source_key': incoming.source_key}
        ) from error
    if result.status is not PutStatus.CREATED:
        response.status_code = status.HTTP_200_OK
    record_notification(source, result.status.value)
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
