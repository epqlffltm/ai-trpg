# asset-server/app/lorebooks/service.py

"""
로어북을 만들고, 고치고, 지우고, 게시한다(#672).

지키는 것.
  - 초안은 만든 사람만 보고 고친다. 남의 것은 없는 것과 같다(LorebookNotFoundError, 404).
  - 만들 수 있는 사람은 캐릭터와 같다. 1~2단계에는 운영자만이다(설정 CHARACTERS_FOR_EVERYONE).
  - 판은 바뀌지 않는다. 게시할 때마다 번호가 하나씩 오른다.
    같은 로어북을 동시에 게시해도 번호가 겹치지 않게 행을 잠근다.
  - 고치거나 게시해도 이미 게시한 캐릭터의 판은 그대로다. 캐릭터를 다시 게시하면 그때의 마지막 판이 들어간다.
"""

import uuid

from server_core.auth.tokens import AccessClaims
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.service import require_maker
from app.lorebooks import repository
from app.lorebooks.documents import build_document
from app.lorebooks.models import Lorebook, LorebookVersion
from app.lorebooks.schemas import LorebookCreate, LorebookUpdate


class LorebookNotFoundError(Exception):
    """그런 로어북(또는 판)이 없다. 남의 로어북도 이것이다."""


async def get_mine(session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID) -> Lorebook:
    """자기 로어북 하나. 없으면 LorebookNotFoundError."""
    lorebook = await repository.find_owned(session, owner_id, lorebook_id)
    if lorebook is None:
        raise LorebookNotFoundError
    return lorebook


async def list_mine(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[Lorebook], int]:
    """자기 로어북의 한 쪽과 전체 개수."""
    return await repository.list_owned(session, owner_id, limit, offset)


async def create_lorebook(
    session: AsyncSession, viewer: AccessClaims, data: LorebookCreate, for_everyone: bool
) -> Lorebook:
    """로어북을 만든다. 만들 수 없는 사람이면 OperatorOnlyError."""
    require_maker(viewer, for_everyone)
    lorebook = Lorebook(owner_id=viewer.user_id, **data.values())
    repository.add(session, lorebook)
    await session.commit()
    await session.refresh(lorebook)
    return lorebook


async def update_lorebook(
    session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID, data: LorebookUpdate
) -> Lorebook:
    """자기 로어북의 초안을 고친다. 게시한 판은 그대로다."""
    lorebook = await get_mine(session, owner_id, lorebook_id)
    for name, value in data.changes().items():
        setattr(lorebook, name, value)
    await session.commit()
    await session.refresh(lorebook)
    return lorebook


async def delete_lorebook(session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID) -> None:
    """
    자기 로어북을 지운다(판도 함께). 이미 게시한 캐릭터의 판에 복사된 것은 그대로다.
    이 로어북을 가리키는 캐릭터의 초안은 다시 게시할 때 막힌다(lorebook_missing).
    """
    lorebook = await get_mine(session, owner_id, lorebook_id)
    await repository.delete(session, lorebook)
    await session.commit()


def build_version(lorebook: Lorebook, note: str) -> LorebookVersion:
    """초안으로 다음 판을 만든다. 아직 저장하지 않는다."""
    return LorebookVersion(
        id=uuid.uuid4(),
        lorebook_id=lorebook.id,
        number=(lorebook.latest_version or 0) + 1,
        note=note,
        document=build_document(lorebook).model_dump(mode='json'),
    )


async def publish(session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID, note: str) -> LorebookVersion:
    """자기 로어북을 게시한다. 막는 것은 없다(항목이 없어도 된다). 행을 잠그고 번호를 정한다."""
    lorebook = await repository.find_owned(session, owner_id, lorebook_id, for_update=True)
    if lorebook is None:
        raise LorebookNotFoundError
    version = build_version(lorebook, note)
    repository.add(session, version)
    lorebook.latest_version = version.number
    lorebook.published_at = func.now()
    await session.commit()
    await session.refresh(version)
    return version


async def list_versions(session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID) -> list[LorebookVersion]:
    """자기 로어북의 판들. 최근 것부터다."""
    await get_mine(session, owner_id, lorebook_id)
    return await repository.list_versions(session, lorebook_id)


async def get_version(
    session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID, number: int
) -> LorebookVersion:
    """자기 로어북의 판 하나. 없으면 LorebookNotFoundError."""
    await get_mine(session, owner_id, lorebook_id)
    version = await repository.find_version(session, lorebook_id, number)
    if version is None:
        raise LorebookNotFoundError
    return version
