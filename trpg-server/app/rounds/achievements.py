# trpg-server/app/rounds/achievements.py

"""
판의 업적. 제작자가 작품에 단 것이다(스팀의 업적과 같다). 인증 서버의 활동 배지와는 다른 것이다.

라운드가 닫힐 때 엔진이 조건을 보고 준다. 방장도 AI(서술, 장부 초안)도 주지 못한다.
  - 조건(when)과 맞추는 법(match)은 퀘스트의 것과 같다(app/rounds/quest_goals.py 의 all_met). 지금의 상태로 본다
  - 퀘스트, 사건, 장, 기한을 모두 본 뒤에 본다. 같은 라운드에 이룬 퀘스트와 넘어간 장을 조건이 본다
  - 받는 사람은 그때 캐릭터를 갖고 앉아 있는 사람 모두다(쓰러지거나 죽은 캐릭터의 사람도). 협동 게임의 업적과 같다
  - 테이블마다 한 번 본다. 받은 것은 테이블에 적는다(table_achievements). 다시 채워져도 다시 주지 않는다
  - 계정마다, 시나리오마다 한 번이다(player_achievements). 다른 테이블에서 이미 받은 사람은 그대로다
  - 받은 것은 이벤트(achievement_earned)로 테이블의 모두에게 보인다. 숨긴 업적도 받은 사람들에게는 보인다

여기의 settle 과 record 는 DB 를 모른다(테이블의 줄과 이벤트만 고친다). 계정마다의 기록은 save 가 따로 적는다.
라운드를 닫는 쪽(app/rounds/service.py)이 settle → record 를 닫힘의 묶음 안에서, save 를 그 뒤에 부른다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.achievements import repository
from app.assets.scenarios.snapshot import AchievementSnapshot, read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.rounds.quest_goals import all_met
from app.tables.models import GameTable, TableAchievement, TableMember, TableMonster, TableNpc


def may_earn(table: GameTable) -> bool:
    """이 테이블의 판에 업적이 있는가. 판을 통째로 읽지 않고 문서의 칸만 본다. 업적이 없는 판은 여기서 끝낸다."""
    return bool(table.content.get('achievements'))


def earned_ids(table: GameTable) -> set[str]:
    """이 테이블에서 이미 받은 업적들."""
    return {row.achievement_id for row in table.achievements}


def receivers(table: GameTable) -> list[TableMember]:
    """업적을 받을 사람들. 캐릭터를 갖고 앉아 있는 사람 모두다. 앉은 차례다."""
    return [member for member in table.members if member.sheet is not None]


def earn(table: GameTable, achievement: AchievementSnapshot, round_number: int) -> dict:
    """업적 하나를 이 테이블에서 받았다고 적고, 이벤트에 적을 모양을 돌려준다."""
    members = receivers(table)
    table.achievements.append(
        TableAchievement(
            achievement_id=achievement.id,
            round_number=round_number,
            user_ids=[str(member.user_id) for member in members],
        )
    )
    return {
        'round': round_number,
        'achievement_id': achievement.id,
        'name': achievement.name,
        'description': achievement.description,
        'image_id': str(achievement.image_id) if achievement.image_id else None,
        'users': [{'user_id': str(member.user_id), 'character_name': member.character_name} for member in members],
    }


def settle_achievements(
    table: GameTable, round_number: int, monsters: list[TableMonster], npcs: list[TableNpc]
) -> list[dict]:
    """
    아직 받지 않은 업적 중 조건이 채워진 것을 판의 순서로 준다. 받은 차례로 이벤트의 모양을 돌려준다.

    받을 사람이 없으면(캐릭터를 가진 사람이 없다) 주지 않는다. 다음에 채워졌을 때 본다.
    monsters 와 npcs 는 테이블의 상태 전부다(장면 밖도). 업적이 없는 판이면 판을 읽지 않는다.
    """
    if not may_earn(table) or not receivers(table):
        return []
    snapshot = read_snapshot(table.content)
    done = earned_ids(table)
    return [
        earn(table, achievement, round_number)
        for achievement in snapshot.achievements
        if achievement.id not in done and all_met(tuple(achievement.when), achievement.match, table, monsters, npcs)
    ]


def record_achievements(session: AsyncSession, table: GameTable, earned: list[dict], group: uuid.UUID) -> None:
    """받은 업적마다 이벤트를 적는다. 닫힘의 묶음(group)에 넣는다. 행한 사람은 없다(엔진이 줬다)."""
    for payload in earned:
        recorder.record(session, table, EventType.ACHIEVEMENT_EARNED, payload=payload, group=group)


async def save(session: AsyncSession, table: GameTable, earned: list[dict]) -> None:
    """
    이번 라운드에 플레이한 사람들과 받은 업적을 계정마다 적는다. 저장은 부르는 쪽이 한다.

    플레이한 사람은 캐릭터를 갖고 앉아 있는 사람이다. 업적이 없는 판에서도 적는다(나중에 업적을 단 판의 달성률).
    """
    await repository.mark_played(session, table.scenario_id, [member.user_id for member in receivers(table)])
    for payload in earned:
        user_ids = [uuid.UUID(user['user_id']) for user in payload['users']]
        await repository.save_earned(session, table.scenario_id, table.id, payload['achievement_id'], user_ids)
