# notification-server/app/mutes/service.py

"""
알림 끄기의 규칙(#525). HTTP 를 모른다. 누구의 설정인지는 부르는 쪽(router.py)이 토큰에서 꺼냈다.

  - 사람마다 종류별로 끈다. 끌 수 있는 종류는 표(app/notifications/catalog.py 의 mutable)가 정한다.
    끌 수 없는 종류나 표에 없는 종류를 끄려 하면 KindNotMutableError 다
  - 끈 종류의 알림은 넣을 때 거른다(app/notifications/service.py). 적지 않으므로 다시 켜도 꺼 둔 동안의 알림은 없다
  - 끄기와 켜기는 몇 번 해도 같다. 이미 꺼진 것을 끄거나 켜진 것을 켜도 오류가 아니다
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.mutes import repository
from app.mutes.schemas import KindMute, MuteSettings
from app.notifications import catalog


class KindNotMutableError(Exception):
    """끌 수 없거나 표에 없는 종류다."""


def ensure_mutable(kind: str) -> None:
    """끌 수 있는 종류가 아니면 KindNotMutableError."""
    if not catalog.is_mutable(kind):
        raise KindNotMutableError


def settings_of(muted: set[str]) -> MuteSettings:
    """끈 종류들을 설정의 모양으로 바꾼다. 끌 수 있는 종류마다 한 칸이다. 끌 수 없게 바뀐 종류의 줄은 싣지 않는다."""
    return MuteSettings(kinds=[KindMute(kind=kind, muted=kind in muted) for kind in catalog.mutable_kinds()])


async def read_settings(session: AsyncSession, user_id: uuid.UUID) -> MuteSettings:
    """이 사람의 알림 끄기 설정을 읽는다."""
    return settings_of(await repository.list_muted(session, user_id))


async def mute(session: AsyncSession, user_id: uuid.UUID, kind: str, now: datetime) -> MuteSettings:
    """이 종류를 끄고 커밋한다. 바뀐 뒤의 설정을 돌려준다. 끌 수 없는 종류면 KindNotMutableError."""
    ensure_mutable(kind)
    await repository.insert_mute(session, user_id, kind, now)
    await session.commit()
    return await read_settings(session, user_id)


async def unmute(session: AsyncSession, user_id: uuid.UUID, kind: str) -> MuteSettings:
    """이 종류를 다시 켜고 커밋한다. 바뀐 뒤의 설정을 돌려준다. 끌 수 없는 종류면 KindNotMutableError."""
    ensure_mutable(kind)
    await repository.delete_mute(session, user_id, kind)
    await session.commit()
    return await read_settings(session, user_id)


async def is_muted(session: AsyncSession, user_id: uuid.UUID, kind: str) -> bool:
    """
    이 사람에게 이 종류의 알림을 넣지 말아야 하는가. 알림을 넣을 때 부른다.

    끌 수 없는 종류는 DB 를 보지 않고 거짓이다. 표에서 끌 수 없게 바뀐 종류의 줄이 남아 있어도 거르지 않는다.
    """
    return catalog.is_mutable(kind) and await repository.is_muted(session, user_id, kind)
