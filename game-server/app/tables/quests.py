# game-server/app/tables/quests.py

"""
테이블의 퀘스트를 다루는 규칙. 무엇이 퀘스트인가, 처음에 어떤 상태인가, 어떻게 바뀌는가, 누가 보는가.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 퀘스트의 행(TableQuest)을 고친다. 저장은 부르는 쪽이 한다.

  - 판의 사건 항목 하나가 퀘스트 하나다. 처음 상태는 판의 퀘스트 규칙의 것이다(규칙이 없으면 숨김).
  - 바뀌는 길: 숨김 → 진행 중 / 성공 / 실패, 진행 중 → 성공 / 실패. 끝난 것은 그대로다. 숨김으로 돌아가지 않는다.
  - 성공하면 보상을 받는다. 앉은 사람의 지금 캐릭터 중 살아 있는 것마다 받는다.
    한 가지의 상한(99 개)에 닿으면 그 사람은 거기까지만 받는다. 다른 사람의 보상은 막지 않는다.
  - 숨긴 퀘스트는 방장만 본다. 드러내야 할 때를 방장이 정하므로 방장은 알아야 한다.
"""

import uuid
from dataclasses import dataclass

from app.assets.scenarios.snapshot import ItemStackSnapshot, Snapshot, quest_entries, quest_rule_of
from app.tables import items, sheets
from app.tables.errors import Conflict, TableConflictError, TableOptionError
from app.tables.items import CatalogItem
from app.tables.models import GameTable, QuestStatus, TableMember, TableQuest

# 끝난 상태. 여기서는 더 바뀌지 않는다
FINISHED = frozenset({QuestStatus.SUCCEEDED, QuestStatus.FAILED})


@dataclass(frozen=True)
class CatalogQuest:
    """판에 있는 퀘스트 하나. 이름은 로어북 사건 항목의 이름, 처음 상태와 보상은 퀘스트 규칙의 것이다."""

    entry_id: uuid.UUID
    name: str
    start: QuestStatus
    reward: list[ItemStackSnapshot]


def catalog(snapshot: Snapshot) -> dict[uuid.UUID, CatalogQuest]:
    """판의 퀘스트 전부. 항목의 id 로 찾는다. 로어북의 순서, 그 안의 항목 순서다."""
    quests = {}
    for entry in quest_entries(snapshot):
        rule = quest_rule_of(snapshot, entry.id)
        quests[entry.id] = CatalogQuest(
            entry_id=entry.id, name=entry.name, start=QuestStatus(rule.start), reward=list(rule.reward)
        )
    return quests


def make_quests(table_id: uuid.UUID, snapshot: Snapshot) -> list[TableQuest]:
    """시작할 때 판의 퀘스트마다 상태를 하나씩 만든다."""
    return [
        TableQuest(table_id=table_id, entry_id=quest.entry_id, status=quest.start)
        for quest in catalog(snapshot).values()
    ]


def find_quest(table: GameTable, entry_id: uuid.UUID) -> TableQuest | None:
    """이 테이블의 그 퀘스트의 행. 없으면 None."""
    return next((quest for quest in table.quests if quest.entry_id == entry_id), None)


def require_quest(
    table: GameTable, quests: dict[uuid.UUID, CatalogQuest], entry_id: uuid.UUID
) -> tuple[TableQuest, CatalogQuest]:
    """
    이 테이블의 퀘스트인지 확인한다. 그 행과 판의 퀘스트를 돌려준다. 아니면 TableOptionError(entry_id).

    사건이 아닌 항목은 퀘스트가 아니다. 퀘스트가 생기기 전에 시작한 테이블에는 퀘스트의 행이 없다.
    """
    row = find_quest(table, entry_id)
    quest = quests.get(entry_id)
    if row is None or quest is None:
        raise TableOptionError('entry_id')
    return row, quest


def require_changeable(current: QuestStatus, to: QuestStatus) -> None:
    """
    지금 상태에서 그 상태로 바꿀 수 있는지 확인한다. 아니면 TableConflictError.

    끝난 것은 quest_finished, 이미 진행 중인 것을 진행 중으로 바꾸면 quest_already_active.
    숨김으로 바꾸는 것은 입력에서 받지 않는다(app/tables/schemas.py 의 QuestChange).
    """
    if current in FINISHED:
        raise TableConflictError(Conflict.QUEST_FINISHED)
    if current == QuestStatus.ACTIVE and to == QuestStatus.ACTIVE:
        raise TableConflictError(Conflict.QUEST_ALREADY_ACTIVE)


def rewarded_members(table: GameTable) -> list[TableMember]:
    """보상을 받는 사람들. 앉은 순서로, 지금 캐릭터가 살아 있는 사람이다."""
    return [member for member in table.members if member.sheet is not None and not sheets.is_dead(member)]


def give_reward(
    table: GameTable, member: TableMember, quest: CatalogQuest, things: dict[uuid.UUID, CatalogItem]
) -> dict:
    """
    한 사람의 지금 캐릭터에게 보상을 준다. 이벤트에 적을 모양으로 돌려준다.

    물건마다 받은 개수(count), 그 뒤의 개수(total), 상한에 닿아 덜 받았는지(capped)를 적는다.
    """
    given = []
    for stack in quest.reward:
        count = items.add_up_to(table.id, member.sheet, stack.entry_id, stack.count)
        given.append(
            {
                'entry_id': str(stack.entry_id),
                'name': things[stack.entry_id].name,
                'count': count,
                'total': items.count_of(member.sheet, stack.entry_id),
                'capped': count < stack.count,
            }
        )
    return {'user_id': str(member.user_id), 'character_name': member.character_name, 'items': given}


def give_rewards(table: GameTable, quest: CatalogQuest, things: dict[uuid.UUID, CatalogItem]) -> list[dict]:
    """보상을 받는 사람마다 준다. 보상이 없는 퀘스트면 아무도 받지 않는다(빈 목록)."""
    if not quest.reward:
        return []
    return [give_reward(table, member, quest, things) for member in rewarded_members(table)]


def in_catalog_order(rows: list[TableQuest], quests: dict[uuid.UUID, CatalogQuest]) -> list[TableQuest]:
    """퀘스트들을 판의 순서로 놓는다. 시작할 때 한 트랜잭션에서 만들어 만든 시각이 같다."""
    order = {entry_id: index for index, entry_id in enumerate(quests)}
    return sorted(rows, key=lambda quest: order[quest.entry_id])


def visible_quests(table: GameTable, quests: dict[uuid.UUID, CatalogQuest], viewer_id: uuid.UUID) -> list[TableQuest]:
    """
    보는 사람에게 보일 퀘스트들. 판의 순서로 놓는다.

    숨긴 것은 방장에게만 보인다. 방장이 아닌 사람에게는 있는지조차 알리지 않는다.
    """
    shown = [quest for quest in table.quests if quest.status != QuestStatus.HIDDEN or viewer_id == table.host_id]
    return in_catalog_order(shown, quests)
