# game-server/app/assets/repository.py

"""
자산을 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 어느 종류의 자산이든 같은 함수를 쓴다.

커밋하지 않는다. 어디까지를 한 묶음으로 저장할지는 서비스가 정한다.

읽는 함수는 모두 "누구의 것인가"를 조건으로 받는다. 남의 자산을 읽는 길이 아예 없다.
지운 자산(deleted_at 이 채워진 것)은 어떤 조회에도 나오지 않는다.

자산이 다른 자산을 가리키는 일과 자산을 지우는 일이 동시에 일어날 수 있다.
둘 다 대상 자산의 행을 먼저 잠근다. 가리키는 쪽은 hold_owned, 지우는 쪽은 lock_owned 다.

model 은 내용 테이블의 모델이다(World 등). 어느 테이블에서 찾을지를 정한다.
"""

import uuid

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetContent, Scenario, ScenarioLorebook


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


async def hold_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, asset_id: uuid.UUID
) -> Content | None:
    """
    자산 하나를 찾고, 이 트랜잭션이 끝날 때까지 지워지지 않게 붙잡는다. 다른 자산이 이것을 가리키려 할 때 쓴다.

    FOR SHARE: 여럿이 동시에 붙잡을 수 있다. 붙잡힌 동안 그 행을 고치려는 쪽(지우기)은 기다린다.
    지우는 쪽이 먼저 잠갔다면 이쪽이 기다리고, 기다린 뒤에는 지워진 것이 보여 None 이 된다.
    """
    query = owned(model, owner_id).where(model.asset_id == asset_id).with_for_update(read=True, of=Asset)
    return await session.scalar(query)


async def lock_owned[Content: AssetContent](
    session: AsyncSession, model: type[Content], owner_id: uuid.UUID, asset_id: uuid.UUID
) -> Content | None:
    """
    자산 하나를 찾고, 이 트랜잭션이 끝날 때까지 혼자 잠근다. "확인하고 나서 쓰는" 일을 할 때 쓴다.

    FOR UPDATE: 같은 자산을 잠그려는 다른 요청과 붙잡으려는 요청(hold_owned)은 이 트랜잭션이 끝날 때까지 기다린다.
    쓰는 곳: 지우기(쓰이는지 확인하고 지운다), 로어북에 항목 더하기(개수를 세고 더한다).
    """
    query = owned(model, owner_id).where(model.asset_id == asset_id).with_for_update(of=Asset)
    return await session.scalar(query)


# "어디에 쓰이는가"를 알려 줄 때 한 번에 돌려주는 최대 개수
MAX_REFERRERS = 20


async def find_referrers(session: AsyncSession, asset_id: uuid.UUID) -> list[Asset]:
    """
    이 자산을 가리키는, 지우지 않은 자산들을 돌려준다. 없으면 빈 목록이다.

    지금 다른 자산을 가리키는 것은 시나리오뿐이다. 가리키는 종류가 늘면 여기에 더한다.
    자기 자산만 가리킬 수 있으므로, 돌려주는 것은 모두 이 자산의 주인의 것이다.
    """
    attached_here = select(ScenarioLorebook.scenario_id).where(ScenarioLorebook.lorebook_id == asset_id)
    points_here = or_(
        Scenario.rulebook_id == asset_id, Scenario.world_id == asset_id, Scenario.asset_id.in_(attached_here)
    )
    query = (
        select(Asset)
        .join(Scenario, Scenario.asset_id == Asset.id)
        .where(points_here, Asset.deleted_at.is_(None))
        .order_by(Asset.created_at, Asset.id)
        .limit(MAX_REFERRERS)
    )
    result = await session.scalars(query)
    return list(result)


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
