# asset-server/app/images/repository.py

"""
그림의 행을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.
"""

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character, CharacterVersion, Visibility
from app.images.models import Image, ImageUse
from app.ratings import Rating


async def add_image(session: AsyncSession, image: Image) -> None:
    """그림의 행을 적는다."""
    session.add(image)
    await session.flush()


async def get_image(session: AsyncSession, image_id: uuid.UUID) -> Image | None:
    """그 id 의 그림. 없으면 None."""
    return await session.get(Image, image_id)


async def owned_ids(session: AsyncSession, owner_id: uuid.UUID, image_ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
    """그 id 들 가운데 이 사람의 그림인 것."""
    if not image_ids:
        return set()
    query = select(Image.id).where(Image.owner_id == owner_id, Image.id.in_(image_ids))
    return set(await session.scalars(query))


def add_uses(session: AsyncSession, version_id: uuid.UUID, image_ids: Collection[uuid.UUID]) -> None:
    """그 판에 쓰인 그림들을 적는다."""
    session.add_all(ImageUse(version_id=version_id, image_id=image_id) for image_id in image_ids)


async def used_publicly(session: AsyncSession, image_id: uuid.UUID, ratings: Sequence[Rating]) -> bool:
    """그 그림이 공개 캐릭터(숨기지 않은 것)의 판에 쓰였고, 그 판의 등급이 ratings 안에 있나."""
    query = select(
        exists()
        .where(ImageUse.image_id == image_id)
        .where(CharacterVersion.id == ImageUse.version_id)
        .where(Character.id == CharacterVersion.character_id)
        .where(Character.visibility == Visibility.PUBLIC, Character.hidden_at.is_(None))
        .where(CharacterVersion.rating.in_(ratings))
    )
    return bool(await session.scalar(query))


async def unused_owned_ids(session: AsyncSession, owner_id: uuid.UUID) -> list[uuid.UUID]:
    """이 사람의 그림 가운데 어느 판에도 쓰이지 않은 것."""
    query = select(Image.id).where(Image.owner_id == owner_id, ~exists().where(ImageUse.image_id == Image.id))
    return list(await session.scalars(query.order_by(Image.id)))


async def delete_unused(session: AsyncSession, image_ids: Collection[uuid.UUID]) -> None:
    """그 id 들의 그림을 지운다. 그사이 판에 쓰인 것은 남긴다."""
    if not image_ids:
        return
    query = delete(Image).where(Image.id.in_(image_ids), ~exists().where(ImageUse.image_id == Image.id))
    await session.execute(query)
