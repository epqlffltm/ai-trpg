# trpg-server/app/operators/publishing.py

"""
제작자가 공개할 수 있는지(#392). 공개하는 쪽(app/listings/service.py)이 부른다.

제재하는 쪽(app/operators/sanctions.py)과 나눈 까닭: 제재는 공개 정보(listings)를 고치고,
공개 정보는 공개할 때 이것을 부른다. 한 모듈에 두면 서로를 불러온다.
"""

import enum
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.operators import repository
from app.operators.models import PublishingBan


class PublicationRefusal(enum.StrEnum):
    """제작자가 공개하지 못하는 까닭(403)."""

    # 운영자가 제재한 판이다. 고쳐서 새 판을 내면 공개할 수 있다
    VERSION_SANCTIONED = 'version_sanctioned'
    # 공개 금지(블랙리스트) 중이다
    PUBLISHING_BANNED = 'publishing_banned'


class PublicationRefusedError(Exception):
    """제작자가 그 판을 공개하지 못한다(403). code 가 까닭이다."""

    def __init__(self, code: PublicationRefusal) -> None:
        super().__init__(code)
        self.code = code


def is_active(ban: PublishingBan | None) -> bool:
    """공개 금지 중인가. 줄이 없거나 풀렸으면 아니다."""
    return ban is not None and ban.lifted_at is None


async def require_publishable(session: AsyncSession, owner_id: uuid.UUID, version_id: uuid.UUID) -> None:
    """
    제작자가 그 판을 공개할 수 있는지 본다. 공개 금지 중이거나 제재된 판이면 PublicationRefusedError.

    공개를 내리는 것은 막지 않는다. 부르는 쪽(app/listings/service.py 의 set_publication)이 공개할 때만 부른다.
    운영자의 공개 금지와 엇갈리지 않게 사람마다 잠그고 본다(시나리오를 잠근 뒤다. 제재와 같은 차례).
    """
    await repository.lock_owner(session, owner_id)
    if is_active(await repository.find_ban(session, owner_id)):
        raise PublicationRefusedError(PublicationRefusal.PUBLISHING_BANNED)
    if await repository.is_sanctioned(session, version_id):
        raise PublicationRefusedError(PublicationRefusal.VERSION_SANCTIONED)
