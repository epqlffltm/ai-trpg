# trpg-server/app/rounds/monster_xp.py

"""
쓰러뜨린 몬스터가 주는 경험치(#286 ②). 라운드가 닫힐 때 엔진이 준다(app/rounds/service.py 의 begin_closing).

  - 판의 몬스터 시트에 적은 경험치(MonsterSnapshot.xp)를 그 마리가 쓰러지거나 죽은 라운드에 준다.
    한 마리마다 한 번이다(TableMonster.xp_given). 쓰러졌다 죽어도, 다시 일어나 또 쓰러져도 다시 주지 않는다.
  - 받는 사람: 그 마리가 있던 장소에 서 있는 죽지 않은 캐릭터들이다(쓰러진 사람도 싸움에 있었다).
    맵이 없는 판이면(서 있는 곳이 없다) 죽지 않은 캐릭터 모두다.
  - 나누는 법은 시나리오의 xp_split 이다. 각자 다(each) 또는 받는 사람 수로 나눔(share, 나머지는 버린다).
  - 성장이 없는 규칙이면 아무것도 하지 않는다(게시할 때 막으므로 경험치를 적은 판은 성장이 있다).
  - 행동의 판정과 수치의 변화를 모두 본 뒤, 퀘스트를 보기 전에 준다. 받은 경험치로 그 라운드의 퀘스트가 바뀌지 않는다.
  - 이벤트는 마리마다 experience_gained(어느 마리, 받은 사람마다 받은 것)이고, 레벨이 오른 사람마다
    character_leveled 가 잇는다.

DB 를 모른다(이벤트를 적는 record 말고). 마리의 칸과 시트만 고친다. 저장은 부른 쪽이 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import XpSplit
from app.engine.ruleset import Progression
from app.events import recorder
from app.events.models import EventType
from app.rounds.experience import record_leveled
from app.rounds.monster_scene import SceneMonster
from app.tables import growth, sheets
from app.tables.content import snapshot_of
from app.tables.models import GameTable, NpcStatus, TableMember

# 경험치를 준 것의 종류. 이벤트의 source.kind 에 적는다
MONSTER = 'monster'


def is_defeated(monster: SceneMonster) -> bool:
    """쓰러지거나 죽었고 아직 경험치를 주지 않은 마리인가."""
    return monster.state.status != NpcStatus.ALIVE and not monster.state.xp_given


def receivers(table: GameTable, monster: SceneMonster) -> list[TableMember]:
    """
    그 마리의 경험치를 받는 사람들. 앉은 순서다.

    그 마리가 있던 장소에 서 있는 죽지 않은 캐릭터다. 서 있는 곳이 없는 캐릭터(맵이 없는 판)는 어디서든 받는다.
    """
    return [
        member
        for member in table.members
        if member.sheet is not None
        and not sheets.is_dead(member)
        and member.sheet.place_id in (None, monster.state.place_id)
    ]


def give(
    table: GameTable, monster: SceneMonster, round_number: int, split: XpSplit, progression: Progression
) -> dict | None:
    """그 마리의 경험치를 준다. 주었다고 적는다. 이벤트에 적을 모양을 돌려준다. 받은 사람이 없으면 None."""
    monster.state.xp_given = True
    gains = growth.grant(receivers(table, monster), monster.definition.xp, split, progression)
    if not gains:
        return None
    source = {'kind': MONSTER, 'id': str(monster.state.id), 'name': monster.name}
    return {'round': round_number, 'source': source, 'split': split, 'gains': gains}


def settle(table: GameTable, round_number: int, monsters: list[SceneMonster]) -> list[dict]:
    """
    이번 장면에서 쓰러지거나 죽은 마리마다 경험치를 준다. 장면의 차례로, 이벤트에 적을 모양들을 돌려준다.

    경험치를 적지 않은 마리도 주었다고 적는다(다시 보지 않게). 성장이 없는 규칙이면 판만 읽고 아무것도 하지 않는다.
    """
    defeated = [monster for monster in monsters if is_defeated(monster)]
    if not defeated:
        return []
    snapshot = snapshot_of(table)
    progression = snapshot.rulebook.rules.progression
    if progression is None:
        return []
    given = [give(table, monster, round_number, snapshot.xp_split, progression) for monster in defeated]
    return [payload for payload in given if payload is not None]


def record(session: AsyncSession, table: GameTable, given: list[dict], group: uuid.UUID) -> None:
    """마리마다 experience_gained 를 적고, 레벨이 오른 사람마다 character_leveled 를 잇는다. 닫힘의 묶음이다."""
    for payload in given:
        event = recorder.record(session, table, EventType.EXPERIENCE_GAINED, payload=payload, group=group)
        record_leveled(session, table, payload['gains'], cause=event)
