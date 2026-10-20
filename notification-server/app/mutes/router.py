# notification-server/app/mutes/router.py

"""
사용자가 알림의 종류별로 끄고 켜는 API(#525). 인증 서버가 발급한 access 토큰으로 누구인지 안다(app/auth).

    GET    /api/v1/notification/me/notifications/mutes           끌 수 있는 종류마다 껐는지
    PUT    /api/v1/notification/me/notifications/mutes/{kind}    그 종류를 끈다
    DELETE /api/v1/notification/me/notifications/mutes/{kind}    그 종류를 다시 켠다

  - 셋 다 바뀐 뒤의 설정 전체를 200 으로 돌려준다. 화면은 받은 것으로 단추를 다시 그린다
  - 끌 수 없는 종류(결제, 제재 등)나 표에 없는 종류면 422 다(detail.code: kind_not_mutable)
  - 누구의 설정인지는 토큰에서만 정한다. 남의 설정을 부를 길이 없다
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.core.database import get_session
from app.mutes import service
from app.mutes.schemas import MuteSettings
from app.notifications.models import KIND_MAX_LENGTH

router = APIRouter(prefix='/me/notifications/mutes', tags=['inbox'])

Session = Annotated[AsyncSession, Depends(get_session)]
Kind = Annotated[str, Path(min_length=1, max_length=KIND_MAX_LENGTH)]

NOT_MUTABLE_RESPONSE = {status.HTTP_422_UNPROCESSABLE_CONTENT: {'description': '끌 수 없거나 표에 없는 종류다'}}


def not_mutable(kind: str) -> HTTPException:
    """끌 수 없는 종류의 응답."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={'code': 'kind_not_mutable', 'kind': kind}
    )


@router.get('', response_model=MuteSettings, status_code=status.HTTP_200_OK)
async def read_mutes(user: CurrentUser, session: Session) -> MuteSettings:
    """끌 수 있는 종류마다 껐는지 읽는다."""
    return await service.read_settings(session, user.user_id)


@router.put('/{kind}', response_model=MuteSettings, status_code=status.HTTP_200_OK, responses=NOT_MUTABLE_RESPONSE)
async def mute_kind(user: CurrentUser, session: Session, kind: Kind) -> MuteSettings:
    """그 종류를 끈다. 이미 꺼져 있어도 200 이다."""
    try:
        return await service.mute(session, user.user_id, kind, datetime.now(UTC))
    except service.KindNotMutableError as error:
        raise not_mutable(kind) from error


@router.delete('/{kind}', response_model=MuteSettings, status_code=status.HTTP_200_OK, responses=NOT_MUTABLE_RESPONSE)
async def unmute_kind(user: CurrentUser, session: Session, kind: Kind) -> MuteSettings:
    """그 종류를 다시 켠다. 이미 켜져 있어도 200 이다."""
    try:
        return await service.unmute(session, user.user_id, kind)
    except service.KindNotMutableError as error:
        raise not_mutable(kind) from error
