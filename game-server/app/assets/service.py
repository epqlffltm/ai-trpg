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


class AssetInUseError(Exception):
    """
    다른 자산이 이 자산을 가리키고 있어서 지울 수 없다.

    referrers 는 가리키고 있는 자산들이다. 어디서 떼어 내야 하는지 알려 주는 데 쓴다.
    """

    def __init__(self, referrers: list[Asset]) -> None:
        super().__init__()
        self.referrers = referrers


class AssetReferenceError(Exception):
    """
    가리키려는 자산이 없다. 남의 것이거나 지운 것인 경우도 이 예외다.

    field 는 입력의 어느 칸이 틀렸는지다(rulebook_id 등).
    """

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


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
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        # null 은 "보내지 않았다"로 본다. 비울 수 있다고 정해 둔 칸만 null 로 비운다
        if value is None and field not in data.clearable:
            continue
        target = content.asset if field in ASSET_FIELDS else content
        setattr(target, field, value)

    # 내용만 바뀌어도 고친 시각은 공통 부분(assets)에 있다. 직접 갱신한다
    touch(content)


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


async def hold_reference(
    session: AsyncSession, model: type[AssetContent], owner_id: uuid.UUID, asset_id: uuid.UUID, field: str
) -> None:
    """
    다른 자산이 가리키려는 자산이 자기 것으로 있는지 확인하고, 저장이 끝날 때까지 지워지지 않게 붙잡는다.

    없으면 AssetReferenceError. 확인과 저장 사이에 그 자산이 지워지는 일을 막는다.
    """
    target = await repository.hold_owned(session, model, owner_id, asset_id)
    if target is None:
        raise AssetReferenceError(field)


async def lock_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, asset_id: uuid.UUID
) -> Content:
    """자기 자산 하나를 혼자 잠그고 돌려준다. 없으면 AssetNotFoundError. 저장이 끝나면 잠금이 풀린다."""
    content = await repository.lock_owned(session, model, owner_id, asset_id)
    if content is None:
        raise AssetNotFoundError
    return content


def touch(content: AssetContent) -> None:
    """자산의 고친 시각을 지금으로 바꾼다. 내용 테이블이나 딸린 행만 바뀌었을 때 부른다."""
    content.asset.updated_at = func.now()


async def list_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Content], int]:
    """자기 자산의 한 쪽과 전체 개수를 돌려준다."""
    contents = await repository.list_owned(session, model, owner_id, limit, offset)
    total = await repository.count_owned(session, model, owner_id)
    return contents, total


async def save_changes[Content: AssetContent](session: AsyncSession, content: Content, data: AssetUpdate) -> Content:
    """이미 찾아 둔 자산에 보낸 칸을 반영하고 저장한다."""
    apply_changes(content, data)
    await session.commit()
    # 고친 시각은 DB 가 정했다. 그 값을 다시 읽어 온다
    await session.refresh(content.asset)
    return content


async def update_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, asset_id: uuid.UUID, data: AssetUpdate
) -> Content:
    """자기 자산을 고친다. 없으면 AssetNotFoundError."""
    content = await get_owned(session, model, owner_id, asset_id)
    return await save_changes(session, content, data)


async def delete_owned(
    session: AsyncSession, model: type[AssetContent], owner_id: uuid.UUID, asset_id: uuid.UUID
) -> None:
    """
    자기 자산을 지운다. 없으면 AssetNotFoundError, 다른 자산이 가리키고 있으면 AssetInUseError.

    행을 지우지 않고 지운 시각을 적는다. 그 뒤로는 어떤 조회에도 나오지 않는다.
    """
    # 먼저 잠그고, 그다음에 쓰이는지 본다. 순서가 반대면 보고 난 뒤에 누가 가리킬 수 있다
    content = await lock_owned(session, model, owner_id, asset_id)
    referrers = await repository.find_referrers(session, asset_id)
    if referrers:
        raise AssetInUseError(referrers)

    content.asset.deleted_at = func.now()
    await session.commit()
