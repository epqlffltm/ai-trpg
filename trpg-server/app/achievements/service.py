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
from app.achievements.schemas import ScenarioAchievementOut, ScenarioAchievements
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
