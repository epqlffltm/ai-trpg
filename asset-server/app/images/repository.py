# asset-server/app/images/repository.py

"""
그림의 행을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.images.models import Image


async def add_image(session: AsyncSession, image: Image) -> None:
    """그림의 행을 적는다."""
    session.add(image)
    await session.flush()


async def get_image(session: AsyncSession, image_id: uuid.UUID) -> Image | None:
    """그 id 의 그림. 없으면 None."""
    return await session.get(Image, image_id)
