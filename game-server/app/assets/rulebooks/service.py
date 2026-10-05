# game-server/app/assets/rulebooks/service.py

"""
룰북을 만들고, 읽고, 고치고, 지운다.

규칙의 대부분은 모든 자산에 공통이라 app/assets/service.py 에 있다.
여기에는 룰북만의 것(입력에서 룰북을 만들고 템플릿의 규칙을 채우는 것)과,
공통 규칙에 "룰북"을 넘겨 부르는 함수가 있다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.models import AssetType, Rulebook
from app.assets.rulebooks.schemas import RulebookCreate, RulebookUpdate
from app.engine.templates import from_template


def build_rulebook(owner_id: uuid.UUID, data: RulebookCreate) -> Rulebook:
    """
    입력에서 룰북 객체를 만든다. 아직 저장하지 않는다.

    고른 템플릿의 규칙을 복사해 넣는다. DB 에 문서로 들어가므로 JSON 으로 옮길 수 있는 값으로 바꾼다.
    """
    asset = assets.build_asset(owner_id, AssetType.RULEBOOK, data)
    rules = from_template(data.template).model_dump(mode='json')
    return Rulebook(asset=asset, gm_guide=data.gm_guide, rules=rules)


async def create_rulebook(session: AsyncSession, owner_id: uuid.UUID, data: RulebookCreate) -> Rulebook:
    """룰북을 만든다."""
    return await assets.create(session, build_rulebook(owner_id, data))


async def get_rulebook(session: AsyncSession, owner_id: uuid.UUID, rulebook_id: uuid.UUID) -> Rulebook:
    """자기 룰북 하나를 돌려준다. 없으면 AssetNotFoundError."""
    return await assets.get_owned(session, Rulebook, owner_id, rulebook_id)


async def list_rulebooks(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Rulebook], int]:
    """자기 룰북의 한 쪽과 전체 개수를 돌려준다."""
    return await assets.list_owned(session, Rulebook, owner_id, limit, offset)


async def update_rulebook(
    session: AsyncSession, owner_id: uuid.UUID, rulebook_id: uuid.UUID, data: RulebookUpdate
) -> Rulebook:
    """자기 룰북을 고친다. 없으면 AssetNotFoundError."""
    return await assets.update_owned(session, Rulebook, owner_id, rulebook_id, data)


async def delete_rulebook(session: AsyncSession, owner_id: uuid.UUID, rulebook_id: uuid.UUID) -> None:
    """자기 룰북을 지운다. 없으면 AssetNotFoundError."""
    await assets.delete_owned(session, Rulebook, owner_id, rulebook_id)
