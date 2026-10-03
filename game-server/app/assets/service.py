# game-server/app/assets/service.py

"""
모든 자산에 똑같이 적용되는 규칙. 종류별 서비스가 이 함수들을 불러 쓴다.

HTTP 를 모른다. 요청이나 상태 코드를 다루지 않고, 안 되는 일은 예외로 알린다.
SQL 을 모른다. DB 에서 읽고 쓰는 일은 repository.py 에 맡긴다.
어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import repository
from app.assets.models import Asset, AssetContent, AssetType
from app.assets.schemas import AssetCreate, AssetUpdate

# 자산의 공통 부분에 속하는 칸. 나머지 칸은 종류별 내용에 속한다
ASSET_FIELDS = {'title', 'description', 'rating'}


class AssetNotFoundError(Exception):
    """
    그런 자산이 없다.

    남의 것인 경우도 이 예외다. "있지만 네 것이 아니다"라고 알려 주면 그 ID 의 자산이 있다는 것이 드러난다.
    """


def build_asset(owner_id: uuid.UUID, asset_type: AssetType, data: AssetCreate) -> Asset:
    """입력에서 자산의 공통 부분을 만든다. 아직 저장하지 않는다."""
    return Asset(
        owner_id=owner_id,
        type=asset_type,
        title=data.title,
        description=data.description,
        rating=data.rating,
    )


def apply_changes(content: AssetContent, data: AssetUpdate) -> None:
    """보낸 칸만 자산에 반영한다. 공통 칸은 공통 부분에, 나머지는 내용에 적는다."""
    # exclude_unset: 요청에 실제로 들어 있던 칸만 꺼낸다. 보내지 않은 칸을 None 으로 덮어쓰지 않는다
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        target = content.asset if field in ASSET_FIELDS else content
        setattr(target, field, value)

    # 내용만 바뀌어도 고친 시각은 공통 부분(assets)에 있다. 직접 갱신한다
    content.asset.updated_at = func.now()


async def create[Content: AssetContent](session: AsyncSession, content: Content) -> Content:
    """자산을 저장한다. 공통 부분과 내용이 한 묶음으로 저장된다."""
    repository.add(session, content)
    await session.commit()
    return content


async def get_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, asset_id: uuid.UUID
) -> Content:
    """자기 자산 하나를 돌려준다. 없으면 AssetNotFoundError."""
    content = await repository.find_owned(session, model, owner_id, asset_id)
    if content is None:
        raise AssetNotFoundError
    return content


async def list_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Content], int]:
    """자기 자산의 한 쪽과 전체 개수를 돌려준다."""
    contents = await repository.list_owned(session, model, owner_id, limit, offset)
    total = await repository.count_owned(session, model, owner_id)
    return contents, total


async def update_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, asset_id: uuid.UUID, data: AssetUpdate
) -> Content:
    """자기 자산을 고친다. 없으면 AssetNotFoundError."""
    content = await get_owned(session, model, owner_id, asset_id)
    apply_changes(content, data)
    await session.commit()
    # 고친 시각은 DB 가 정했다. 그 값을 다시 읽어 온다
    await session.refresh(content.asset)
    return content


async def delete_owned(
    session: AsyncSession, model: type[AssetContent], owner_id: uuid.UUID, asset_id: uuid.UUID
) -> None:
    """
    자기 자산을 지운다. 없으면 AssetNotFoundError.

    행을 지우지 않고 지운 시각을 적는다. 그 뒤로는 어떤 조회에도 나오지 않는다.
    """
    content = await get_owned(session, model, owner_id, asset_id)
    content.asset.deleted_at = func.now()
    await session.commit()
