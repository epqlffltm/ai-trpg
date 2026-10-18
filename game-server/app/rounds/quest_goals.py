# game-server/app/rounds/quest_goals.py

"""
라운드가 닫힐 때 이룬 퀘스트를 성공으로 바꾼다(app/rounds/service.py 의 begin_closing, #367).

성공은 엔진만 정한다. 방장은 PC 라서 결과를 정하지 않고, AI 는 상태를 바꾸지 못한다.
판의 퀘스트 규칙에 적은 조건(app/assets/models.py 의 QuestConditionKind)을 지금의 상태로 본다.
  - reach_place: 그 장소에 죽지 않은 캐릭터가 서 있다.
  - defeat_monster: 그 몬스터가 count 마리 이상 쓰러지거나 죽었다. 테이블 전체의 마리를 센다(장면 밖도).
  - hold_item: 죽지 않은 캐릭터들이 그 물건을 모두 합쳐 count 개 이상 가졌다.
  - defeat_npc: 그 인물이 쓰러지거나 죽었다.
조건이 여럿이면 퀘스트마다 정한 대로 모두(all) 또는 하나라도(any) 채워야 한다. 조건이 없는 퀘스트는 성공하지 않는다.

  - 이번 라운드의 판정(이동, 타격, 물건, 휴식)을 모두 끝낸 뒤에 본다. 그 라운드에 한 일이 그 라운드에 반영된다.
  - 기한보다 먼저 본다. 기한이 넘어 실패로 바뀌기 전 마지막 라운드에 이루었으면 성공이다.
  - 숨긴 퀘스트도 본다. 채워졌으면 드러내며 바로 성공이다. 우연히 이룬 일도 이룬 것이다.
  - 성공하면 보상을 준다(app/tables/quests.py 의 give_rewards). 사람이 한 일이 아니므로 누가 했는지는 비우고
    까닭(conditions_met)을 적는다. 기한의 실패(app/rounds/deadlines.py)와 같은 모양이다.

DB 를 모른다. 잠근 테이블의 퀘스트 행과 소지품을 고치고 이벤트에 적을 모양을 돌려준다.
이벤트를 적는 것은 record_successes 다.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import QuestConditionKind, QuestMatch
from app.assets.scenarios.snapshot import QuestConditionSnapshot, read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.tables import items, quests, sheets
from app.tables.items import CatalogItem
from app.tables.models import GameTable, NpcStatus, QuestStatus, TableMember, TableMonster, TableNpc, TableQuest
from app.tables.quest_changes import describe
from app.tables.quests import FINISHED, CatalogQuest

# 서버가 퀘스트를 바꾼 까닭. 이벤트의 reason 에 적는다
CONDITIONS_MET = 'conditions_met'


def living(table: GameTable) -> list[TableMember]:
    """조건을 채울 수 있는 사람들. 지금 캐릭터가 있고 죽지 않았다. 쓰러져 있어도 그 자리에 있고 물건을 가졌다."""
    return [member for member in table.members if member.sheet is not None and not sheets.is_dead(member)]


def reached(table: GameTable, place_id: uuid.UUID) -> bool:
    """그 장소에 죽지 않은 캐릭터가 서 있는가."""
    return any(member.sheet.place_id == place_id for member in living(table))


def held(table: GameTable, entry_id: uuid.UUID) -> int:
    """죽지 않은 캐릭터들이 가진 그 물건의 개수를 모두 합친 것."""
    return sum(items.count_of(member.sheet, entry_id) for member in living(table))


def defeated_monsters(monsters: Iterable[TableMonster], monster_id: uuid.UUID) -> int:
    """그 몬스터 중 쓰러지거나 죽은 마리 수."""
    return sum(1 for monster in monsters if monster.monster_id == monster_id and monster.status != NpcStatus.ALIVE)


def npc_defeated(npcs: Iterable[TableNpc], entry_id: uuid.UUID) -> bool:
    """그 인물이 쓰러지거나 죽었는가. 상태가 없는 인물(아직 만들지 않았다)은 아니다."""
    return any(npc.entry_id == entry_id and npc.status != NpcStatus.ALIVE for npc in npcs)


def is_met(
    condition: QuestConditionSnapshot, table: GameTable, monsters: list[TableMonster], npcs: list[TableNpc]
) -> bool:
    """조건 하나가 지금 채워졌는가."""
    if condition.kind == QuestConditionKind.REACH_PLACE:
        return reached(table, condition.target)
    if condition.kind == QuestConditionKind.HOLD_ITEM:
        return held(table, condition.target) >= condition.count
    if condition.kind == QuestConditionKind.DEFEAT_MONSTER:
        return defeated_monsters(monsters, condition.target) >= condition.count
    return npc_defeated(npcs, condition.target)


def is_achieved(quest: CatalogQuest, table: GameTable, monsters: list[TableMonster], npcs: list[TableNpc]) -> bool:
    """그 퀘스트를 이루었는가. 조건이 없으면 이루지 않는다. 모두(all) 또는 하나라도(any)는 퀘스트가 정한다."""
    if not quest.conditions:
        return False
    met = [is_met(condition, table, monsters, npcs) for condition in quest.conditions]
    return all(met) if quest.match == QuestMatch.ALL else any(met)


def succeed(table: GameTable, row: TableQuest, quest: CatalogQuest, things: dict[uuid.UUID, CatalogItem]) -> dict:
    """
    이룬 퀘스트 하나를 성공으로 바꾸고 보상을 준다. 이벤트에 적을 모양을 돌려준다.

    숨긴 채로 이룬 것에는 기한이 끝나는 시각을 적지 않는다. 드러나는 순간 끝났다.
    """
    previous = row.status
    row.status = QuestStatus.SUCCEEDED
    row.changed_at = func.now()
    rewards = quests.give_rewards(table, quest, things)
    return describe(quest, previous, QuestStatus.SUCCEEDED, rewards, row.due_at, reason=CONDITIONS_MET)


def open_quests(table: GameTable) -> list[TableQuest]:
    """아직 끝나지 않은 퀘스트들(숨김, 진행 중). 이 중에서 이룬 것을 찾는다."""
    return [row for row in table.quests if row.status not in FINISHED]


def complete_quests(table: GameTable, monsters: list[TableMonster], npcs: list[TableNpc]) -> list[dict]:
    """
    이룬 퀘스트를 모두 성공으로 바꾼다. 판의 순서로, 이벤트에 적을 모양들을 돌려준다.

    monsters 와 npcs 는 테이블의 상태 전부다(장면 밖도). 끝나지 않은 퀘스트가 없으면 판을 읽지 않는다.
    """
    rows = open_quests(table)
    if not rows:
        return []
    snapshot = read_snapshot(table.content)
    catalog = quests.catalog(snapshot)
    things = items.catalog(snapshot)
    achieved = [row for row in rows if is_achieved(catalog[row.entry_id], table, monsters, npcs)]
    return [succeed(table, row, catalog[row.entry_id], things) for row in quests.in_catalog_order(achieved, catalog)]


def record_successes(session: AsyncSession, table: GameTable, successes: list[dict], group: uuid.UUID) -> None:
    """이루어 성공한 퀘스트마다 이벤트를 적는다. 닫힘의 묶음(group)에 넣는다. 행한 사람은 없다."""
    for payload in successes:
        recorder.record(session, table, EventType.QUEST_CHANGED, payload=payload, group=group)
