# trpg-server/app/rounds/quest_goals.py

"""
라운드가 닫힐 때 숨긴 퀘스트를 드러내고, 이룬 퀘스트를 성공으로, 실패할 조건이 채워진 퀘스트를 실패로 바꾼다
(app/rounds/service.py 의 begin_closing, #367).

드러내기, 성공, 실패는 엔진만 정한다. 방장은 PC 라서 결과를 정하지 않고, AI 는 상태를 바꾸지 못한다.
판의 퀘스트 규칙에 적은 조건(app/assets/models.py 의 QuestConditionKind)을 지금의 상태로 본다.
  - reach_place: 그 장소에 죽지 않은 캐릭터가 서 있다.
  - defeat_monster: 그 몬스터가 count 마리 이상 쓰러지거나 죽었다. 테이블 전체의 마리를 센다(장면 밖도).
  - hold_item: 죽지 않은 캐릭터들이 그 물건을 모두 합쳐 count 개 이상 가졌다.
    consume 이면 이룰 때 그만큼 가져간다(배달, app/rounds/quest_handover.py).
  - defeat_npc: 그 인물이 쓰러지거나 죽었다. npc_dead: 그 인물이 죽었다(쓰러진 것은 아니다).
  - lose_item: 죽지 않은 캐릭터들이 그 물건을 모두 합쳐 count 개보다 적게 가졌다. 실패하는 조건에만 있다.
  - quest_succeeded, quest_failed: 그 퀘스트가 성공했다, 실패했다(퀘스트 잇기). 드러나는 조건과 실패하는 조건에 있다.
조건이 여럿이면 퀘스트마다 정한 대로 모두(all) 또는 하나라도(any) 채워야 한다.

  - 드러나기(reveal): 숨긴 퀘스트의 드러나는 조건이 채워지면 진행 중으로 바꾼다. 기한은 그때부터 센다.
    조건이 없으면 드러나지 않는다. 이루어야만 드러난다.
  - 성공(conditions): 숨김이나 진행 중인 퀘스트의 이루는 조건이 채워지면 성공으로 바꾸고, 가져가는 물건을 뺀 뒤
    보상을 준다. 조건이 없으면 성공하지 않는다. 숨긴 채로 채웠으면 드러내며 바로 성공이다. 우연히 이룬 일도 이룬 것이다.
  - 성공은 판의 순서로 하나씩 보고 바로 바꾼다. 앞 퀘스트가 가져간 물건은 뒤 퀘스트가 셀 때 이미 없다.
    같은 물건을 가져가는 퀘스트 둘을 한 번에 이루지 않는다. 앞 퀘스트의 보상은 뒤 퀘스트가 셀 때 이미 있다.
  - 실패(fail): 진행 중인 퀘스트의 실패하는 조건이 채워지면 실패로 바꾼다. 조건이 없으면 기한으로만 실패한다.
    숨긴 퀘스트는 실패하지 않는다. 드러난 뒤에 본다(드러난 그 라운드에 이미 채워졌으면 그 라운드에 실패한다).
  - 드러내기, 성공, 실패의 차례로 본다. 그 라운드에 드러난 퀘스트도 그 라운드에 이룰 수 있다.
    같은 라운드에 이루는 조건과 실패하는 조건이 함께 채워졌으면 성공이다(먼저 본다).
    퀘스트 잇기가 있으므로 바뀐 것이 없을 때까지 되풀이한다(settle_quests). 퀘스트마다 많아야 두 번 바뀌므로 끝난다.
  - 이번 라운드의 판정(이동, 타격, 물건, 휴식)을 모두 끝낸 뒤에 본다. 그 라운드에 한 일이 그 라운드에 반영된다.
  - 기한보다 먼저 본다. 기한이 넘어 실패로 바뀌기 전 마지막 라운드에 이루었으면 성공이다.
    기한의 실패를 기다리는 퀘스트는 실패를 적은 뒤 한 번 더 본다(begin_closing).
  - 사람이 한 일이 아니므로 누가 했는지는 비우고 까닭(conditions_met)을 적는다.
    기한의 실패(app/rounds/deadlines.py)와 같은 모양이다.

DB 를 모른다. 잠근 테이블의 퀘스트 행과 소지품을 고치고 이벤트에 적을 모양을 돌려준다.
이벤트를 적는 것은 record_changes 다.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import QuestConditionKind, QuestMatch
from app.assets.scenarios.snapshot import QuestConditionSnapshot, read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.rounds.quest_handover import hand_over
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


def npc_dead(npcs: Iterable[TableNpc], entry_id: uuid.UUID) -> bool:
    """그 인물이 죽었는가. 쓰러진 것은 아니다. 상태가 없는 인물(아직 만들지 않았다)은 아니다."""
    return any(npc.entry_id == entry_id and npc.status == NpcStatus.DEAD for npc in npcs)


def quest_ended(table: GameTable, entry_id: uuid.UUID, status: QuestStatus) -> bool:
    """그 퀘스트가 그 상태(성공, 실패)로 끝났는가. 퀘스트의 행이 없으면 아니다."""
    row = quests.find_quest(table, entry_id)
    return row is not None and row.status == status


# 퀘스트 잇기의 조건마다 기다리는 끝난 상태
LINKED_STATUS = {
    QuestConditionKind.QUEST_SUCCEEDED: QuestStatus.SUCCEEDED,
    QuestConditionKind.QUEST_FAILED: QuestStatus.FAILED,
}


def is_met(
    condition: QuestConditionSnapshot, table: GameTable, monsters: list[TableMonster], npcs: list[TableNpc]
) -> bool:
    """조건 하나가 지금 채워졌는가."""
    if condition.kind in LINKED_STATUS:
        return quest_ended(table, condition.target, LINKED_STATUS[condition.kind])
    if condition.kind == QuestConditionKind.REACH_PLACE:
        return reached(table, condition.target)
    if condition.kind == QuestConditionKind.HOLD_ITEM:
        return held(table, condition.target) >= condition.count
    if condition.kind == QuestConditionKind.LOSE_ITEM:
        return held(table, condition.target) < condition.count
    if condition.kind == QuestConditionKind.DEFEAT_MONSTER:
        return defeated_monsters(monsters, condition.target) >= condition.count
    if condition.kind == QuestConditionKind.NPC_DEAD:
        return npc_dead(npcs, condition.target)
    return npc_defeated(npcs, condition.target)


def all_met(
    conditions: tuple[QuestConditionSnapshot, ...],
    match: QuestMatch,
    table: GameTable,
    monsters: list[TableMonster],
    npcs: list[TableNpc],
) -> bool:
    """조건들이 채워졌는가. 조건이 없으면 아니다. 모두(all) 또는 하나라도(any)는 퀘스트가 정한다."""
    if not conditions:
        return False
    met = [is_met(condition, table, monsters, npcs) for condition in conditions]
    return all(met) if match == QuestMatch.ALL else any(met)


def is_achieved(quest: CatalogQuest, table: GameTable, monsters: list[TableMonster], npcs: list[TableNpc]) -> bool:
    """그 퀘스트를 이루었는가. 이루는 조건(conditions)을 본다."""
    return all_met(quest.conditions, quest.match, table, monsters, npcs)


def is_revealed(quest: CatalogQuest, table: GameTable, monsters: list[TableMonster], npcs: list[TableNpc]) -> bool:
    """그 퀘스트가 드러날 때인가. 드러나는 조건(reveal)을 본다."""
    return all_met(quest.reveal, quest.reveal_match, table, monsters, npcs)


def is_failing(quest: CatalogQuest, table: GameTable, monsters: list[TableMonster], npcs: list[TableNpc]) -> bool:
    """그 퀘스트가 실패할 때인가. 실패하는 조건(fail)을 본다. 조건이 없으면 아니다(기한으로만 실패한다)."""
    return all_met(quest.fail, quest.fail_match, table, monsters, npcs)


def consumed_conditions(
    quest: CatalogQuest, table: GameTable, monsters: list[TableMonster], npcs: list[TableNpc]
) -> list[QuestConditionSnapshot]:
    """
    이룰 때 물건을 가져가는 조건들. consume 을 적은 물건 갖기 중 지금 채워진 것이다.

    하나라도(any)로 이뤘으면 채운 조건의 물건만 가져간다. 채우지 않은 조건의 물건은 모자라서 가져갈 수 없다.
    """
    return [
        condition for condition in quest.conditions if condition.consume and is_met(condition, table, monsters, npcs)
    ]


def succeed(
    table: GameTable,
    row: TableQuest,
    quest: CatalogQuest,
    things: dict[uuid.UUID, CatalogItem],
    consumed: list[QuestConditionSnapshot],
) -> dict:
    """
    이룬 퀘스트 하나를 성공으로 바꾸고, 가져가는 물건을 뺀 뒤 보상을 준다. 이벤트에 적을 모양을 돌려준다.

    숨긴 채로 이룬 것에는 기한이 끝나는 시각을 적지 않는다. 드러나는 순간 끝났다.
    """
    previous = row.status
    row.status = QuestStatus.SUCCEEDED
    row.changed_at = func.now()
    handed = hand_over(living(table), consumed, things)
    rewards = quests.give_rewards(table, quest, things)
    return describe(quest, previous, QuestStatus.SUCCEEDED, rewards, row.due_at, reason=CONDITIONS_MET, consumed=handed)


def show(table: GameTable, row: TableQuest, quest: CatalogQuest) -> dict:
    """
    드러날 때가 된 숨긴 퀘스트 하나를 진행 중으로 바꾼다. 이벤트에 적을 모양을 돌려준다.

    판의 기한이 있으면 이 라운드가 열린 시각부터 센다(app/tables/quests.py 의 reveal).
    """
    row.status = QuestStatus.ACTIVE
    row.changed_at = func.now()
    quests.reveal(row, quest, table.clock.minutes)
    return describe(quest, QuestStatus.HIDDEN, QuestStatus.ACTIVE, [], row.due_at, reason=CONDITIONS_MET)


def fail(row: TableQuest, quest: CatalogQuest) -> dict:
    """
    실패할 조건이 채워진 진행 중인 퀘스트 하나를 실패로 바꾼다. 이벤트에 적을 모양을 돌려준다.

    보상도 가져가는 것도 없다. 기한이 끝나는 시각은 적어 둔 그대로 싣는다(기한의 실패와 같은 모양).
    """
    row.status = QuestStatus.FAILED
    row.changed_at = func.now()
    return describe(quest, QuestStatus.ACTIVE, QuestStatus.FAILED, [], row.due_at, reason=CONDITIONS_MET)


def open_quests(table: GameTable) -> list[TableQuest]:
    """아직 끝나지 않은 퀘스트들(숨김, 진행 중). 이 중에서 이룬 것을 찾는다."""
    return [row for row in table.quests if row.status not in FINISHED]


def active_quests(table: GameTable) -> list[TableQuest]:
    """진행 중인 퀘스트들. 이 중에서 실패할 것을 찾는다. 숨긴 것은 실패하지 않는다."""
    return [row for row in table.quests if row.status == QuestStatus.ACTIVE]


def hidden_quests(table: GameTable) -> list[TableQuest]:
    """숨긴 퀘스트들. 이 중에서 드러날 것을 찾는다."""
    return [row for row in table.quests if row.status == QuestStatus.HIDDEN]


def reveal_quests(
    table: GameTable, catalog: dict[uuid.UUID, CatalogQuest], monsters: list[TableMonster], npcs: list[TableNpc]
) -> list[dict]:
    """
    드러날 때가 된 숨긴 퀘스트를 모두 진행 중으로 바꾼다. 판의 순서로, 이벤트에 적을 모양들을 돌려준다.

    모두 본 뒤에 바꾼다. 한 퀘스트가 드러난 것이 같은 바퀴의 다른 퀘스트를 드러내지 않는다(잇기는 끝난 것만 본다).
    """
    shown = [row for row in hidden_quests(table) if is_revealed(catalog[row.entry_id], table, monsters, npcs)]
    return [show(table, row, catalog[row.entry_id]) for row in quests.in_catalog_order(shown, catalog)]


def complete_quests(
    table: GameTable,
    catalog: dict[uuid.UUID, CatalogQuest],
    things: dict[uuid.UUID, CatalogItem],
    monsters: list[TableMonster],
    npcs: list[TableNpc],
) -> list[dict]:
    """
    이룬 퀘스트를 모두 성공으로 바꾼다. 판의 순서로, 이벤트에 적을 모양들을 돌려준다.

    하나씩 보고 바로 바꾼다. 앞 퀘스트가 가져간 물건과 준 보상이 뒤 퀘스트의 조건에 반영된다.
    """
    changes = []
    for row in quests.in_catalog_order(open_quests(table), catalog):
        quest = catalog[row.entry_id]
        if is_achieved(quest, table, monsters, npcs):
            consumed = consumed_conditions(quest, table, monsters, npcs)
            changes.append(succeed(table, row, quest, things, consumed))
    return changes


def fail_quests(
    table: GameTable, catalog: dict[uuid.UUID, CatalogQuest], monsters: list[TableMonster], npcs: list[TableNpc]
) -> list[dict]:
    """
    실패할 조건이 채워진 진행 중인 퀘스트를 모두 실패로 바꾼다. 판의 순서로, 이벤트에 적을 모양들을 돌려준다.

    모두 본 뒤에 바꾼다. 한 퀘스트의 실패가 같은 바퀴의 다른 퀘스트를 실패시키지 않는다(잇기는 다음 바퀴에 본다).
    """
    failing = [row for row in active_quests(table) if is_failing(catalog[row.entry_id], table, monsters, npcs)]
    return [fail(row, catalog[row.entry_id]) for row in quests.in_catalog_order(failing, catalog)]


def settle_quests(table: GameTable, monsters: list[TableMonster], npcs: list[TableNpc]) -> list[dict]:
    """
    드러낼 것을 드러내고, 이룬 것을 성공으로, 실패할 것을 실패로 바꾼다. 바뀐 것이 없을 때까지 되풀이한다.
    바뀐 차례로 돌려준다.

    한 바퀴에 드러내기, 성공, 실패의 차례로 본다. 성공이나 실패가 다른 퀘스트를 드러내거나 실패시키면(잇기)
    다음 바퀴에 바뀐다. 퀘스트마다 많아야 두 번(숨김 → 진행 중 → 성공 또는 실패) 바뀌므로 되풀이는 끝난다.
    monsters 와 npcs 는 테이블의 상태 전부다(장면 밖도). 끝나지 않은 퀘스트가 없으면 판을 읽지 않는다.
    """
    if not open_quests(table):
        return []
    snapshot = read_snapshot(table.content)
    catalog = quests.catalog(snapshot)
    things = items.catalog(snapshot)
    changes: list[dict] = []
    while True:
        changed = reveal_quests(table, catalog, monsters, npcs)
        changed.extend(complete_quests(table, catalog, things, monsters, npcs))
        changed.extend(fail_quests(table, catalog, monsters, npcs))
        if not changed:
            return changes
        changes.extend(changed)


def record_changes(session: AsyncSession, table: GameTable, changes: list[dict], group: uuid.UUID) -> None:
    """엔진이 바꾼 퀘스트마다 이벤트를 적는다. 닫힘의 묶음(group)에 넣는다. 행한 사람은 없다."""
    for payload in changes:
        recorder.record(session, table, EventType.QUEST_CHANGED, payload=payload, group=group)
