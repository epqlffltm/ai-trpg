# game-server/app/assets/lorebooks/service.py

"""
로어북과 그 항목을 만들고, 읽고, 고치고, 지운다.

로어북 자신의 규칙은 모든 자산에 공통이라 app/assets/service.py 에 있다.
여기에는 항목의 규칙이 있다. 항목은 로어북에 딸려 있어서, 로어북의 주인만 다룰 수 있다.
항목이 바뀌면 로어북이 바뀐 것이다. 로어북의 고친 시각을 함께 갱신한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.lorebooks import repository
from app.assets.lorebooks.schemas import EntryCreate, EntryUpdate, LorebookCreate, LorebookUpdate
from app.assets.models import LOREBOOK_MAX_ENTRIES, AssetType, Lorebook, LoreEntry
from app.assets.service import AssetNotFoundError


class LorebookFullError(Exception):
    """로어북의 항목이 상한에 닿아 더 넣을 수 없다."""


# --- 로어북 ---


def build_lorebook(owner_id: uuid.UUID, data: LorebookCreate) -> Lorebook:
    """입력에서 로어북 객체를 만든다. 아직 저장하지 않는다."""
    return Lorebook(asset=assets.build_asset(owner_id, AssetType.LOREBOOK, data))


async def create_lorebook(session: AsyncSession, owner_id: uuid.UUID, data: LorebookCreate) -> Lorebook:
    """로어북을 만든다. 항목은 없다."""
    return await assets.create(session, build_lorebook(owner_id, data))


async def get_lorebook(session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID) -> Lorebook:
    """자기 로어북 하나를 돌려준다. 없으면 AssetNotFoundError."""
    return await assets.get_owned(session, Lorebook, owner_id, lorebook_id)


async def list_lorebooks(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Lorebook], int]:
    """자기 로어북의 한 쪽과 전체 개수를 돌려준다."""
    return await assets.list_owned(session, Lorebook, owner_id, limit, offset)


async def update_lorebook(
    session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID, data: LorebookUpdate
) -> Lorebook:
    """자기 로어북을 고친다. 없으면 AssetNotFoundError."""
    return await assets.update_owned(session, Lorebook, owner_id, lorebook_id, data)


async def delete_lorebook(session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID) -> None:
    """자기 로어북을 지운다. 없으면 AssetNotFoundError. 항목은 로어북과 함께 보이지 않게 된다."""
    await assets.delete_owned(session, Lorebook, owner_id, lorebook_id)


# --- 항목 ---


def build_entry(lorebook_id: uuid.UUID, data: EntryCreate) -> LoreEntry:
    """입력에서 항목 객체를 만든다. 아직 저장하지 않는다."""
    return LoreEntry(lorebook_id=lorebook_id, name=data.name, keywords=data.keywords, content=data.content)


def apply_entry_changes(entry: LoreEntry, data: EntryUpdate) -> None:
    """보낸 칸만 항목에 반영한다."""
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(entry, field, value)


async def get_entry(session: AsyncSession, lorebook_id: uuid.UUID, entry_id: uuid.UUID) -> LoreEntry:
    """로어북의 항목 하나를 돌려준다. 없으면 AssetNotFoundError."""
    entry = await repository.find_entry(session, lorebook_id, entry_id)
    if entry is None:
        raise AssetNotFoundError
    return entry


async def add_entry(session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID, data: EntryCreate) -> LoreEntry:
    """
    자기 로어북에 항목을 더한다. 로어북이 없으면 AssetNotFoundError, 가득 찼으면 LorebookFullError.

    개수를 세고 나서 더한다. 두 요청이 동시에 세면 둘 다 "아직 자리가 있다"고 보고 상한을 넘긴다.
    그래서 세기 전에 로어북을 잠근다. 같은 로어북에 더하려는 다른 요청은 이 저장이 끝날 때까지 기다린다.
    """
    lorebook = await assets.lock_owned(session, Lorebook, owner_id, lorebook_id)
    if await repository.count_entries(session, lorebook_id) >= LOREBOOK_MAX_ENTRIES:
        raise LorebookFullError

    entry = build_entry(lorebook_id, data)
    repository.add_entry(session, entry)
    assets.touch(lorebook)
    await session.commit()
    return entry


async def list_entries(session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID) -> list[LoreEntry]:
    """자기 로어북의 항목을 만든 순서대로 전부 돌려준다. 로어북이 없으면 AssetNotFoundError."""
    await get_lorebook(session, owner_id, lorebook_id)
    return await repository.list_entries(session, lorebook_id)


async def update_entry(
    session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID, entry_id: uuid.UUID, data: EntryUpdate
) -> LoreEntry:
    """자기 로어북의 항목을 고친다. 로어북이나 항목이 없으면 AssetNotFoundError."""
    lorebook = await get_lorebook(session, owner_id, lorebook_id)
    entry = await get_entry(session, lorebook_id, entry_id)
    apply_entry_changes(entry, data)
    assets.touch(lorebook)
    await session.commit()
    # 고친 시각은 DB 가 정했다. 그 값을 다시 읽어 온다
    await session.refresh(entry)
    return entry


async def delete_entry(session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    """자기 로어북의 항목을 지운다. 로어북이나 항목이 없으면 AssetNotFoundError."""
    lorebook = await get_lorebook(session, owner_id, lorebook_id)
    entry = await get_entry(session, lorebook_id, entry_id)
    await repository.delete_entry(session, entry)
    assets.touch(lorebook)
    await session.commit()
