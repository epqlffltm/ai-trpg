# game-server/app/assets/scenarios/service.py

"""
시나리오를 만들고, 읽고, 고치고, 지운다.

규칙의 대부분은 모든 자산에 공통이라 app/assets/service.py 에 있다.
여기에는 시나리오만의 것이 있다. 시나리오는 다른 자산(룰북, 세계관, 로어북)을 가리킨다.
가리키는 자산은 자기 것이어야 하고, 지운 것이면 안 된다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.models import AssetContent, AssetType, Lorebook, Rulebook, Scenario, World
from app.assets.scenarios.schemas import ScenarioCreate, ScenarioUpdate

# 다른 자산을 하나 가리키는 칸과, 그 칸이 가리킬 수 있는 종류.
# 적힌 순서대로 잠근다. 순서가 늘 같아야 두 요청이 서로를 기다리며 멈추는 일(교착)이 없다.
# 로어북(lorebook_ids)은 여러 개라 따로 다룬다. 이 칸들 다음에, ID 순서로 잠근다
REFERENCES: dict[str, type[AssetContent]] = {'rulebook_id': Rulebook, 'world_id': World}


def build_scenario(owner_id: uuid.UUID, data: ScenarioCreate) -> Scenario:
    """입력에서 시나리오 객체를 만든다. 아직 저장하지 않는다."""
    asset = assets.build_asset(owner_id, AssetType.SCENARIO, data, rating=data.rating)
    return Scenario(
        asset=asset,
        rulebook_id=data.rulebook_id,
        world_id=data.world_id,
        lorebook_ids=data.lorebook_ids,
        openings=data.openings,
        recommended_players=data.recommended_players.model_dump(),
        pregens=[pregen.model_dump() for pregen in data.pregens],
        character_modes=list(data.character_modes),
        default_sheet=data.default_sheet.model_dump() if data.default_sheet else None,
    )


async def hold_references(session: AsyncSession, owner_id: uuid.UUID, data: ScenarioCreate | ScenarioUpdate) -> None:
    """
    입력이 가리키는 자산을 확인하고 저장이 끝날 때까지 붙잡는다. 없는 것이 있으면 AssetReferenceError.

    비워 둔 칸은 보지 않는다.
    """
    for field, model in REFERENCES.items():
        asset_id = getattr(data, field)
        if asset_id is not None:
            await assets.hold_reference(session, model, owner_id, asset_id, field)

    for lorebook_id in sorted(data.lorebook_ids or []):
        await assets.hold_reference(session, Lorebook, owner_id, lorebook_id, 'lorebook_ids')


async def create_scenario(session: AsyncSession, owner_id: uuid.UUID, data: ScenarioCreate) -> Scenario:
    """시나리오를 만든다. 가리키는 자산이 없으면 AssetReferenceError."""
    await hold_references(session, owner_id, data)
    return await assets.create(session, build_scenario(owner_id, data))


async def get_scenario(session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID) -> Scenario:
    """자기 시나리오 하나를 돌려준다. 없으면 AssetNotFoundError."""
    return await assets.get_owned(session, Scenario, owner_id, scenario_id)


async def list_scenarios(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Scenario], int]:
    """자기 시나리오의 한 쪽과 전체 개수를 돌려준다."""
    return await assets.list_owned(session, Scenario, owner_id, limit, offset)


async def update_scenario(
    session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID, data: ScenarioUpdate
) -> Scenario:
    """
    자기 시나리오를 고친다. 없으면 AssetNotFoundError, 가리키는 자산이 없으면 AssetReferenceError.

    시나리오를 잠그고 고친다. 로어북의 목록은 "지금 붙은 것과 비교해서" 바꾸므로,
    두 요청이 같은 옛 목록을 보고 각자 바꾸면 둘의 것이 합쳐져 상한을 넘길 수 있다.
    """
    scenario = await assets.lock_owned(session, Scenario, owner_id, scenario_id)
    await hold_references(session, owner_id, data)
    return await assets.save_changes(session, scenario, data)


async def delete_scenario(session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID) -> None:
    """자기 시나리오를 지운다. 없으면 AssetNotFoundError."""
    await assets.delete_owned(session, Scenario, owner_id, scenario_id)
