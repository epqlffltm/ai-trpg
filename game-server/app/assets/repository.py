# game-server/app/assets/repository.py

"""
자산을 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 어느 종류의 자산이든 같은 함수를 쓴다.

커밋하지 않는다. 어디까지를 한 묶음으로 저장할지는 서비스가 정한다.

읽는 함수는 모두 "누구의 것인가"를 조건으로 받는다. 남의 자산을 읽는 길이 아예 없다.
지운 자산(deleted_at 이 채워진 것)은 어떤 조회에도 나오지 않는다.

model 은 내용 테이블의 모델이다(World 등). 어느 테이블에서 찾을지를 정한다.
"""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetContent


def owned[Content: AssetContent](model: type[Content], owner_id: uuid.UUID) -> Select[tuple[Content]]:
    """한 사람이 가진, 지우지 않은 자산을 고르는 조건. 읽는 함수들이 함께 쓴다."""
    return select(model).join(model.asset).where(Asset.owner_id == owner_id, Asset.deleted_at.is_(None))


def add(session: AsyncSession, content: AssetContent) -> None:
    """새 자산을 세션에 올린다. 공통 부분(content.asset)도 함께 저장된다."""
    session.add(content)


async def find_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, asset_id: uuid.UUID
) -> Content | None:
    """자산 하나를 찾는다. 없거나, 남의 것이거나, 지운 것이면 None."""
    query = owned(model, owner_id).where(model.asset_id == asset_id)
    return await session.scalar(query)


async def list_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, limit: int, offset: int
) -> list[Content]:
    """한 사람의 자산을 최근에 만든 것부터 돌려준다."""
    # 만든 시각이 같은 것끼리의 순서도 정해 둔다. 정하지 않으면 쪽을 넘길 때 같은 것이 두 번 나오거나 빠진다
    query = owned(model, owner_id).order_by(Asset.created_at.desc(), Asset.id).limit(limit).offset(offset)
    result = await session.scalars(query)
    return list(result)


async def count_owned(session: AsyncSession, model: type[AssetContent], owner_id: uuid.UUID) -> int:
    """한 사람의 자산이 몇 개인지 센다."""
    query = select(func.count()).select_from(owned(model, owner_id).subquery())
    return await session.scalar(query) or 0
