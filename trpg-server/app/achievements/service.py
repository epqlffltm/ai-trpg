# trpg-server/app/achievements/service.py

"""
공개된 시나리오의 업적을 보이는 일. 판의 업적에 받은 수와 보는 사람이 받은 때를 붙이고, 숨긴 것을 가린다.

어느 시나리오를 볼 수 있는지는 공개 정보의 규칙을 그대로 쓴다(app/listings/service.py 의 get_public).
공개하지 않은 것, 볼 수 없는 등급인 것은 없는 것(404)이다.
"""

import uuid
from datetime import datetime

from server_core.auth.tokens import AccessClaims
from sqlalchemy.ext.asyncio import AsyncSession

from app.achievements import repository
from app.achievements.repository import EarnedRow
from app.achievements.schemas import MyAchievementOut, MyAchievementPage, ScenarioAchievementOut, ScenarioAchievements
from app.assets.ratings import allowed_ratings
from app.assets.scenarios.snapshot import AchievementSnapshot, read_snapshot
from app.listings.service import get_public


def shown(achievement: AchievementSnapshot, earned_at: datetime | None, earned_count: int) -> ScenarioAchievementOut:
    """업적 하나를 응답의 모양으로. 숨긴 업적을 받기 전이면 이름, 설명, 그림을 가린다."""
    veiled = achievement.hidden and earned_at is None
    return ScenarioAchievementOut(
        id=achievement.id,
        hidden=achievement.hidden,
        name=None if veiled else achievement.name,
        description=None if veiled else achievement.description,
        image_id=None if veiled else achievement.image_id,
        earned_at=earned_at,
        earned_count=earned_count,
    )


async def mine(session: AsyncSession, viewer: AccessClaims | None, scenario_id: uuid.UUID) -> dict[str, datetime]:
    """보는 사람이 그 시나리오에서 받은 업적들. 로그인하지 않았으면 비어 있다."""
    if viewer is None:
        return {}
    return await repository.earned_by(session, viewer.user_id, scenario_id)


async def scenario_achievements(
    session: AsyncSession, viewer: AccessClaims | None, scenario_id: uuid.UUID
) -> ScenarioAchievements:
    """공개된 시나리오의 업적들. 볼 수 없으면 AssetNotFoundError."""
    _, _, version = await get_public(session, viewer, scenario_id)
    achievements = read_snapshot(version.snapshot).achievements
    counts = await repository.count_earned(session, scenario_id)
    earned = await mine(session, viewer, scenario_id)
    items = [shown(one, earned.get(one.id), counts.get(one.id, 0)) for one in achievements]
    return ScenarioAchievements(items=items, players=await repository.count_players(session, scenario_id))


def find_definition(achievements: list[dict] | None, achievement_id: str) -> AchievementSnapshot | None:
    """판의 업적들(문서의 칸 그대로)에서 그 업적. 판이 없거나 그 업적을 뺐으면 None."""
    for entry in achievements or []:
        if isinstance(entry, dict) and entry.get('id') == achievement_id:
            return AchievementSnapshot.model_validate(entry)
    return None


def to_mine(row: EarnedRow, viewer: AccessClaims) -> MyAchievementOut:
    """받은 업적 하나를 응답의 모양으로. 받은 테이블의 판을 먼저, 없으면 지금 공개 중인 판의 정의를 쓴다."""
    found = find_definition(row.played, row.achievement_id) or find_definition(row.listed, row.achievement_id)
    listed = (
        not row.deleted
        and row.listed is not None
        and row.listing_rating is not None
        and row.listing_rating in allowed_ratings(viewer)
    )
    return MyAchievementOut(
        scenario_id=row.scenario_id,
        scenario_title=row.title,
        listed=listed,
        achievement_id=row.achievement_id,
        name=found.name if found else None,
        description=found.description if found else None,
        image_id=found.image_id if found else None,
        earned_at=row.earned_at,
    )


async def my_achievements(session: AsyncSession, viewer: AccessClaims, limit: int, offset: int) -> MyAchievementPage:
    """보는 사람이 받은 업적의 한 쪽. 모든 시나리오의 것이다."""
    rows = await repository.earned_page(session, viewer.user_id, limit, offset)
    total = await repository.count_earned_by(session, viewer.user_id)
    return MyAchievementPage(items=[to_mine(row, viewer) for row in rows], total=total)
