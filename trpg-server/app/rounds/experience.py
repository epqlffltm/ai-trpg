# trpg-server/app/rounds/experience.py

"""
경험치를 받아 레벨이 오른 것을 이벤트로 적는다(#286). 퀘스트의 보상, 쓰러뜨린 몬스터, 판의 사건이 함께 쓴다.

받은 사람마다의 모양은 {user_id, character_name, xp} 다. xp 는 app/tables/growth.py 의 gain 이 돌려준 것이다.
레벨이 오른 사람마다 character_leveled 를 그 경험치를 준 이벤트(cause)나 묶음(group)에 잇는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType, TableEvent
from app.tables import growth
from app.tables.models import GameTable


def leveled_payload(reward: dict) -> dict:
    """레벨이 오른 캐릭터의 이벤트(character_leveled). 누구이고, 몇에서 몇으로, 그 뒤의 경험치·최대 HP·쌓인 점수다."""
    gained = reward['xp']
    return {
        'user_id': reward['user_id'],
        'character_name': reward['character_name'],
        'previous_level': gained['previous_level'],
        'level': gained['level'],
        'xp': gained['total'],
        'max_hp': gained['max_hp'],
        'points': gained['points'],
    }


def record_leveled(
    session: AsyncSession,
    table: GameTable,
    rewards: list[dict],
    group: uuid.UUID | None = None,
    cause: TableEvent | None = None,
) -> None:
    """받은 사람 중 레벨이 오른 사람마다 character_leveled 를 적는다. 받은 차례다."""
    for reward in rewards:
        if growth.leveled(reward.get('xp')):
            payload = leveled_payload(reward)
            recorder.record(session, table, EventType.CHARACTER_LEVELED, payload=payload, group=group, cause=cause)
