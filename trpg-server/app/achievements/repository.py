# trpg-server/app/achievements/repository.py

"""
시나리오 업적의 계정마다의 기록을 읽고 쓴다(app/achievements/models.py). 쿼리만 한다. 저장(commit)은 부르는 쪽이 한다.

같은 사람이 같은 업적을 다시 받거나 같은 시나리오를 다시 플레이해도 줄은 하나다(기본 키).
그래서 쓰기는 모두 "있으면 그대로"(ON CONFLICT DO NOTHING)다. 두 테이블이 함께 줘도 막히지 않는다.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.achievements.models import PlayerAchievement, ScenarioPlayer


async def mark_played(session: AsyncSession, scenario_id: uuid.UUID, user_ids: Sequence[uuid.UUID]) -> None:
    """그 사람들이 그 시나리오를 플레이했다고 적는다. 이미 적힌 사람은 그대로다."""
    if not user_ids:
        return
    rows = [{'scenario_id': scenario_id, 'user_id': user_id} for user_id in user_ids]
    await session.execute(insert(ScenarioPlayer).values(rows).on_conflict_do_nothing())


async def save_earned(
    session: AsyncSession,
    scenario_id: uuid.UUID,
    table_id: uuid.UUID | None,
    achievement_id: str,
    user_ids: Sequence[uuid.UUID],
) -> None:
    """
    그 사람들이 그 업적을 받았다고 적는다. 이미 받은 사람은 그대로다(처음 받은 때와 테이블이 남는다).

    table_id 는 받은 테이블이다. 모르면 None 이다.
    """
    if not user_ids:
        return
    rows = [
        {'user_id': user_id, 'scenario_id': scenario_id, 'achievement_id': achievement_id, 'table_id': table_id}
        for user_id in user_ids
    ]
    await session.execute(insert(PlayerAchievement).values(rows).on_conflict_do_nothing())


async def count_players(session: AsyncSession, scenario_id: uuid.UUID) -> int:
    """그 시나리오를 플레이한 사람의 수."""
    query = select(func.count()).select_from(ScenarioPlayer).where(ScenarioPlayer.scenario_id == scenario_id)
    return await session.scalar(query) or 0


async def count_earned(session: AsyncSession, scenario_id: uuid.UUID) -> dict[str, int]:
    """그 시나리오의 업적마다 받은 사람의 수. 아무도 받지 않은 업적은 없다."""
    query = (
        select(PlayerAchievement.achievement_id, func.count())
        .where(PlayerAchievement.scenario_id == scenario_id)
        .group_by(PlayerAchievement.achievement_id)
    )
    return {achievement_id: count for achievement_id, count in await session.execute(query)}


async def earned_by(session: AsyncSession, user_id: uuid.UUID, scenario_id: uuid.UUID) -> dict[str, datetime]:
    """그 사람이 그 시나리오에서 받은 업적마다 받은 때."""
    query = select(PlayerAchievement.achievement_id, PlayerAchievement.earned_at).where(
        PlayerAchievement.user_id == user_id, PlayerAchievement.scenario_id == scenario_id
    )
    return {achievement_id: earned_at for achievement_id, earned_at in await session.execute(query)}


async def delete_all_of(session: AsyncSession, user_id: uuid.UUID) -> None:
    """그 사람의 업적과 플레이의 기록을 모두 지운다(탈퇴). 저장은 부르는 쪽이 한다."""
    await session.execute(delete(PlayerAchievement).where(PlayerAchievement.user_id == user_id))
    await session.execute(delete(ScenarioPlayer).where(ScenarioPlayer.user_id == user_id))
