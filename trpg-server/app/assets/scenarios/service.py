# trpg-server/app/assets/scenarios/service.py

"""
시나리오를 만들고, 읽고, 고치고, 지운다.

규칙의 대부분은 모든 자산에 공통이라 app/assets/service.py 에 있다.
여기에는 시나리오만의 것이 있다. 시나리오는 다른 자산(룰북, 세계관, 로어북, 몬스터 도감)을 가리킨다.
가리키는 자산은 자기 것이어야 하고, 지운 것이면 안 된다.
프리젠의 캐릭터 그림(#983)도 자기가 올린 것이어야 한다.
"""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import repository as asset_rows
from app.assets import service as assets
from app.assets.bestiaries.models import Bestiary
from app.assets.models import AssetContent, AssetType, Lorebook, Rating, Rulebook, Scenario, World
from app.assets.ratings import ALL_AGES_ONLY, require_rating
from app.assets.scenarios import mine
from app.assets.scenarios.mine import MineOrder, MyScenario
from app.assets.scenarios.recommended_model import require_recommendable
from app.assets.scenarios.schemas import Achievement, EntryPicture, Pregen, ScenarioCreate, ScenarioUpdate
from app.portraits import repository as portraits

# 프리젠의 캐릭터 그림이 틀렸을 때 AssetReferenceError 에 싣는 칸의 이름
PREGEN_IMAGE_FIELD = 'pregens.image_id'
# 로어 항목마다의 그림(#1163)이 틀렸을 때의 칸의 이름
PICTURE_IMAGE_FIELD = 'pictures.image_id'
# 업적의 그림이 틀렸을 때의 칸의 이름
ACHIEVEMENT_IMAGE_FIELD = 'achievements.image_id'

# 다른 자산을 하나 가리키는 칸과, 그 칸이 가리킬 수 있는 종류.
# 적힌 순서대로 잠근다. 순서가 늘 같아야 두 요청이 서로를 기다리며 멈추는 일(교착)이 없다.
# 로어북(lorebook_ids)과 도감(bestiary_ids)은 여러 개라 따로 다룬다.
# 이 칸들 다음에 로어북, 도감의 차례로, 각각 ID 순서로 잠근다
REFERENCES: dict[str, type[AssetContent]] = {'rulebook_id': Rulebook, 'world_id': World}


def build_scenario(owner_id: uuid.UUID, data: ScenarioCreate) -> Scenario:
    """입력에서 시나리오 객체를 만든다. 아직 저장하지 않는다."""
    asset = assets.build_asset(owner_id, AssetType.SCENARIO, data, rating=data.rating)
    return Scenario(
        asset=asset,
        rulebook_id=data.rulebook_id,
        world_id=data.world_id,
        lorebook_ids=data.lorebook_ids,
        bestiary_ids=data.bestiary_ids,
        openings=data.openings,
        recommended_players=data.recommended_players.model_dump(),
        pregens=[pregen.model_dump() for pregen in data.pregens],
        character_modes=list(data.character_modes),
        default_sheet=data.default_sheet.model_dump() if data.default_sheet else None,
        npc_sheets=[npc_sheet.model_dump() for npc_sheet in data.npc_sheets],
        default_npc_sheet=data.default_npc_sheet.model_dump() if data.default_npc_sheet else None,
        monster_sheets=[monster_sheet.model_dump() for monster_sheet in data.monster_sheets],
        encounters=[encounter.model_dump() for encounter in data.encounters],
        items=[rule.model_dump() for rule in data.items],
        starting_items=[stack.model_dump() for stack in data.starting_items],
        currency=data.currency.model_dump() if data.currency else None,
        quests=[quest.model_dump() for quest in data.quests],
        start_place=data.start_place,
        routes=[route.model_dump() for route in data.routes],
        landmarks=list(data.landmarks),
        place_items=[rule.model_dump() for rule in data.place_items],
        covers=[rule.model_dump() for rule in data.covers],
        traps=[trap.model_dump() for trap in data.traps],
        pictures=[picture.model_dump() for picture in data.pictures],
        submaps=[submap.model_dump() for submap in data.submaps],
        wanders=[table.model_dump() for table in data.wanders],
        happenings=[rule.model_dump() for rule in data.happenings],
        chapters=[chapter.model_dump() for chapter in data.chapters],
        achievements=[achievement.model_dump() for achievement in data.achievements],
        npc_places=[place.model_dump() for place in data.npc_places],
        player_made_hp=data.player_made_hp.model_dump() if data.player_made_hp else None,
        reroll_allowed=data.reroll_allowed,
        xp_split=data.xp_split,
        improvised_encounters=data.improvised_encounters,
        narration_style=data.narration_style,
        narration_model=data.narration_model,
        clock=data.clock.model_dump(),
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

    for bestiary_id in sorted(data.bestiary_ids or []):
        await assets.hold_reference(session, Bestiary, owner_id, bestiary_id, 'bestiary_ids')


def pregen_images(pregens: Sequence[Pregen] | None) -> set[uuid.UUID]:
    """프리젠들이 붙인 캐릭터 그림의 id 들. 보내지 않았으면 비어 있다."""
    return {pregen.image_id for pregen in pregens or [] if pregen.image_id is not None}


async def require_owned(session: AsyncSession, owner_id: uuid.UUID, wanted: set[uuid.UUID], field: str) -> None:
    """
    그림이 모두 자기가 올린 것인지 본다. 아니면 field 를 실은 AssetReferenceError.

    남의 그림, 없는 그림, 이 서버에 올리지 않은 asset 의 그림(장면 그림 등)은 모두 같다.
    """
    if wanted - await portraits.owned_ids(session, owner_id, wanted):
        raise assets.AssetReferenceError(field)


async def require_own_portraits(session: AsyncSession, owner_id: uuid.UUID, pregens: Sequence[Pregen] | None) -> None:
    """프리젠의 캐릭터 그림이 모두 자기가 올린 것인지 본다. 아니면 AssetReferenceError(pregens.image_id)."""
    await require_owned(session, owner_id, pregen_images(pregens), PREGEN_IMAGE_FIELD)


async def require_own_pictures(
    session: AsyncSession, owner_id: uuid.UUID, pictures: Sequence[EntryPicture] | None
) -> None:
    """로어 항목마다의 그림(#1163)이 모두 자기가 올린 것인지 본다. 아니면 AssetReferenceError(pictures.image_id)."""
    wanted = {image for picture in pictures or [] for image in picture.images()}
    await require_owned(session, owner_id, wanted, PICTURE_IMAGE_FIELD)


async def require_own_achievement_images(
    session: AsyncSession, owner_id: uuid.UUID, achievements: Sequence[Achievement] | None
) -> None:
    """업적의 그림이 모두 자기가 올린 것인지 본다. 아니면 AssetReferenceError(achievements.image_id)."""
    wanted = {achievement.image_id for achievement in achievements or [] if achievement.image_id is not None}
    await require_owned(session, owner_id, wanted, ACHIEVEMENT_IMAGE_FIELD)


async def create_scenario(
    session: AsyncSession,
    owner_id: uuid.UUID,
    data: ScenarioCreate,
    today: date,
    allowed: Sequence[Rating] = ALL_AGES_ONLY,
) -> Scenario:
    """
    시나리오를 만든다. 가리키는 자산이 없으면 AssetReferenceError.

    추천 서술 모델이 서비스 중인 모델이 아니면 RecommendedModelError. today 는 은퇴했는지 볼 날이다.
    allowed 는 만드는 사람이 쓸 수 있는 등급이다(app/assets/ratings.py). 그 밖의 등급이면 AdultContentRequiredError.
    """
    require_rating(data.rating, allowed)
    await require_recommendable(session, data.narration_model, today)
    await hold_references(session, owner_id, data)
    await require_own_portraits(session, owner_id, data.pregens)
    await require_own_pictures(session, owner_id, data.pictures)
    await require_own_achievement_images(session, owner_id, data.achievements)
    return await assets.create(session, build_scenario(owner_id, data))


async def get_scenario(session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID) -> Scenario:
    """자기 시나리오 하나를 돌려준다. 없으면 AssetNotFoundError."""
    return await assets.get_owned(session, Scenario, owner_id, scenario_id)


async def list_scenarios(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int, order: MineOrder = MineOrder.CREATED
) -> tuple[list[MyScenario], int]:
    """
    자기 시나리오의 한 쪽과 전체 개수를 돌려준다. 줄마다 쓰인 수와 관심 수, 공개 상태가 있다(#1165).

    order 는 차례다(app/assets/scenarios/mine.py). 기본은 최근에 만든 것부터다.
    """
    rows = await mine.list_mine(session, owner_id, limit, offset, order)
    return rows, await asset_rows.count_owned(session, Scenario, owner_id)


async def require_model_change(session: AsyncSession, scenario: Scenario, data: ScenarioUpdate, today: date) -> None:
    """
    고친 뒤의 추천 서술 모델을 확인한다. 아니면 RecommendedModelError.

    보낸 모델은 서비스 중이어야 한다. 보내지 않았으면 지금의 모델을 그대로 두므로 다시 보지 않는다.
    지금 모델이 은퇴해도 다른 칸을 고칠 수 있다. 작성자가 알림을 보고 고를 때까지 테이블은 대체 모델로 만든다.
    추천 모델이 없는 옛 시나리오는 모델을 함께 보내야 저장된다.
    """
    if data.narration_model is not None or scenario.narration_model is None:
        await require_recommendable(session, data.narration_model, today)


async def update_scenario(
    session: AsyncSession,
    owner_id: uuid.UUID,
    scenario_id: uuid.UUID,
    data: ScenarioUpdate,
    today: date,
    allowed: Sequence[Rating] = ALL_AGES_ONLY,
) -> Scenario:
    """
    자기 시나리오를 고친다. 없으면 AssetNotFoundError, 가리키는 자산이 없으면 AssetReferenceError,
    추천 서술 모델이 맞지 않으면 RecommendedModelError(require_model_change).

    지금의 등급이나 바꿀 등급이 allowed 에 없으면 AdultContentRequiredError(#390).
    성인용 시나리오는 어느 칸도 고칠 수 없다. 전체 이용가로 내리는 것도 막는다. 그러면 성인용 글이 전체 이용가로 나간다.
    읽기와 지우기는 막지 않는다.

    시나리오를 잠그고 고친다. 로어북과 도감의 목록은 "지금 붙은 것과 비교해서" 바꾸므로,
    두 요청이 같은 옛 목록을 보고 각자 바꾸면 둘의 것이 합쳐져 상한을 넘길 수 있다.
    """
    scenario = await assets.lock_owned(session, Scenario, owner_id, scenario_id)
    require_rating(scenario.asset.rating, allowed)
    if data.rating is not None:
        require_rating(data.rating, allowed)
    await require_model_change(session, scenario, data, today)
    await hold_references(session, owner_id, data)
    await require_own_portraits(session, owner_id, data.pregens)
    await require_own_pictures(session, owner_id, data.pictures)
    await require_own_achievement_images(session, owner_id, data.achievements)
    return await assets.save_changes(session, scenario, data)


async def delete_scenario(session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID) -> None:
    """자기 시나리오를 지운다. 없으면 AssetNotFoundError."""
    await assets.delete_owned(session, Scenario, owner_id, scenario_id)
