# game-server/app/tables/quests.py

"""
테이블의 퀘스트를 다루는 규칙. 무엇이 퀘스트인가, 처음에 어떤 상태인가, 어떻게 바뀌는가, 누가 보는가.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 퀘스트의 행(TableQuest)을 고친다. 저장은 부르는 쪽이 한다.

  - 판의 사건 항목 하나가 퀘스트 하나다. 처음 상태는 판의 퀘스트 규칙의 것이다(규칙이 없으면 숨김).
  - 바뀌는 길: 숨김 → 진행 중 / 성공, 진행 중 → 성공 / 실패. 끝난 것은 그대로다. 숨김으로 돌아가지 않는다.
  - 드러내기와 성공은 엔진만 정한다. 판의 조건을 라운드가 닫힐 때 보고 바꾼다(app/rounds/quest_goals.py).
    방장의 요청은 진행 중인 퀘스트의 실패만 한다(#367).
  - 성공하면 보상을 받는다. 앉은 사람의 지금 캐릭터 중 살아 있는 것마다 받는다.
    한 가지의 상한(99 개)에 닿으면 그 사람은 거기까지만 받는다. 다른 사람의 보상은 막지 않는다.
  - 숨긴 퀘스트는 아무도 보지 않는다. 방장도 PC 라서 다른 사람이 모르는 것을 알면 안 된다.
    방장이 바꾸려 해도 없는 퀘스트처럼 다룬다. 있는지조차 알리지 않는다. 서술자(GM)만 안다.
  - 기한: 판의 규칙에 기한이 있으면 드러날 때(진행 중이 될 때) 끝나는 게임 안의 시각을 적는다.
    처음부터 진행 중인 것은 테이블이 시작하는 시각부터, 숨겼다가 드러난 것은 드러난 라운드가 열린 시각부터 센다.
    숨긴 채로 바로 끝낸 것에는 적지 않는다. 기한이 지난 것을 실패로 바꾸는 것은 app/rounds/deadlines.py 다.
"""

import uuid
from dataclasses import dataclass

from app.assets.models import QuestMatch
from app.assets.scenarios.snapshot import (
    ItemStackSnapshot,
    QuestConditionSnapshot,
    Snapshot,
    quest_entries,
    quest_rule_of,
)
from app.tables import items, sheets
from app.tables.errors import Conflict, TableConflictError, TableOptionError
from app.tables.items import CatalogItem
from app.tables.models import GameTable, QuestStatus, TableMember, TableQuest

# 끝난 상태. 여기서는 더 바뀌지 않는다
FINISHED = frozenset({QuestStatus.SUCCEEDED, QuestStatus.FAILED})


@dataclass(frozen=True)
class CatalogQuest:
    """
    판에 있는 퀘스트 하나. 이름은 로어북 사건 항목의 이름, 처음 상태와 보상과 기한은 퀘스트 규칙의 것이다.

    time_limit_minutes 는 드러난 때부터 세는 기한(분)이다. 없으면 None.
    conditions 는 이루는 조건, match 는 그것을 맞추는 법이다. 조건이 없으면 성공하지 않는다.
    reveal 은 드러나는 조건, reveal_match 는 그것을 맞추는 법이다. 조건이 없으면 이루어야만 드러난다.
    """

    entry_id: uuid.UUID
    name: str
    start: QuestStatus
    reward: list[ItemStackSnapshot]
    time_limit_minutes: int | None = None
    conditions: tuple[QuestConditionSnapshot, ...] = ()
    match: QuestMatch = QuestMatch.ALL
    reveal: tuple[QuestConditionSnapshot, ...] = ()
    reveal_match: QuestMatch = QuestMatch.ALL


def catalog(snapshot: Snapshot) -> dict[uuid.UUID, CatalogQuest]:
    """판의 퀘스트 전부. 항목의 id 로 찾는다. 로어북의 순서, 그 안의 항목 순서다."""
    quests = {}
    for entry in quest_entries(snapshot):
        rule = quest_rule_of(snapshot, entry.id)
        quests[entry.id] = CatalogQuest(
            entry_id=entry.id,
            name=entry.name,
            start=QuestStatus(rule.start),
            reward=list(rule.reward),
            time_limit_minutes=rule.time_limit_minutes,
            conditions=tuple(rule.conditions),
            match=rule.match,
            reveal=tuple(rule.reveal),
            reveal_match=rule.reveal_match,
        )
    return quests


def due_at_of(quest: CatalogQuest, revealed_at: int) -> int | None:
    """그 시각(분)에 드러나는 퀘스트의 기한이 끝나는 시각. 기한이 없으면 None."""
    if quest.time_limit_minutes is None:
        return None
    return revealed_at + quest.time_limit_minutes


def make_quest(table_id: uuid.UUID, quest: CatalogQuest, now: int) -> TableQuest:
    """시작할 때의 퀘스트 하나. 처음부터 진행 중이면 지금(now)부터 기한을 센다."""
    due_at = due_at_of(quest, now) if quest.start == QuestStatus.ACTIVE else None
    return TableQuest(table_id=table_id, entry_id=quest.entry_id, status=quest.start, due_at=due_at)


def make_quests(table_id: uuid.UUID, snapshot: Snapshot, now: int) -> list[TableQuest]:
    """시작할 때 판의 퀘스트마다 상태를 하나씩 만든다. now 는 테이블이 시작하는 게임 안의 시각(분)이다."""
    return [make_quest(table_id, quest, now) for quest in catalog(snapshot).values()]


def find_quest(table: GameTable, entry_id: uuid.UUID) -> TableQuest | None:
    """이 테이블의 그 퀘스트의 행. 없으면 None."""
    return next((quest for quest in table.quests if quest.entry_id == entry_id), None)


def require_quest(
    table: GameTable, quests: dict[uuid.UUID, CatalogQuest], entry_id: uuid.UUID
) -> tuple[TableQuest, CatalogQuest]:
    """
    사람이 다룰 수 있는 이 테이블의 퀘스트인지 확인한다. 그 행과 판의 퀘스트를 돌려준다.
    아니면 TableOptionError(entry_id).

    사건이 아닌 항목은 퀘스트가 아니다. 퀘스트가 생기기 전에 시작한 테이블에는 퀘스트의 행이 없다.
    숨긴 퀘스트도 없는 것과 같다. 아무에게도 보이지 않으므로 있는지조차 알리지 않는다.
    """
    row = find_quest(table, entry_id)
    quest = quests.get(entry_id)
    if row is None or quest is None or row.status == QuestStatus.HIDDEN:
        raise TableOptionError('entry_id')
    return row, quest


def target_problem(to: QuestStatus) -> Conflict | None:
    """
    사람이 그 상태로 바꿀 수 없는 까닭. 지금 상태와 상관없다. 바꿀 수 있으면 None.

    성공으로 바꾸면 quest_success_by_engine, 진행 중으로(드러내기) 바꾸면 quest_reveal_by_engine 이다.
    둘 다 엔진이 판의 조건을 보고 정한다(app/rounds/quest_goals.py). 사람에게 남은 것은 실패뿐이다.
    """
    if to == QuestStatus.SUCCEEDED:
        return Conflict.QUEST_SUCCESS_BY_ENGINE
    if to == QuestStatus.ACTIVE:
        return Conflict.QUEST_REVEAL_BY_ENGINE
    return None


def change_problem(current: QuestStatus, to: QuestStatus) -> Conflict | None:
    """
    사람이 지금 상태에서 그 상태로 바꿀 수 없는 까닭. 바꿀 수 있으면 None.

    바꿀 상태의 까닭(target_problem)을 먼저 본다. 그다음 끝난 것은 quest_finished 다.
    숨김으로 바꾸는 것은 입력에서 받지 않는다(app/tables/schemas.py 의 QuestChange).
    """
    problem = target_problem(to)
    if problem is not None:
        return problem
    if current in FINISHED:
        return Conflict.QUEST_FINISHED
    return None


def require_target(to: QuestStatus) -> None:
    """사람이 그 상태로 바꿀 수 있는지 확인한다. 아니면 TableConflictError(그 까닭)."""
    problem = target_problem(to)
    if problem is not None:
        raise TableConflictError(problem)


def require_changeable(current: QuestStatus, to: QuestStatus) -> None:
    """지금 상태에서 그 상태로 바꿀 수 있는지 확인한다. 아니면 TableConflictError(그 까닭)."""
    problem = change_problem(current, to)
    if problem is not None:
        raise TableConflictError(problem)


def reveal(row: TableQuest, quest: CatalogQuest, now: int) -> None:
    """진행 중이 된 퀘스트에 기한이 끝나는 시각을 적는다. now 는 드러난 라운드가 열린 시각이다."""
    row.due_at = due_at_of(quest, now)


def is_overdue(row: TableQuest, round_opened_at: int) -> bool:
    """
    기한을 넘겨 실패로 바꿀 퀘스트인가. 진행 중이고, 기한이 이 라운드가 열린 시각이나 그 앞에 끝났다.

    기한이 장면 안에서 끝나도 그 라운드에는 바꾸지 않는다. 그 장면의 결과는 서술이 끝난 뒤에야 보인다.
    그 장면 다음 라운드 하나만큼 틈을 둔다. 그 라운드에 조건을 채우면 성공이고, 닫힐 때까지 그대로면 실패다.
    """
    return row.status == QuestStatus.ACTIVE and row.due_at is not None and row.due_at <= round_opened_at


def overdue_quests(table: GameTable, round_opened_at: int) -> list[TableQuest]:
    """기한을 넘긴 퀘스트들. 테이블에 담긴 순서다(부르는 쪽이 판의 순서로 놓는다)."""
    return [row for row in table.quests if is_overdue(row, round_opened_at)]


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


def visible_quests(table: GameTable, quests: dict[uuid.UUID, CatalogQuest]) -> list[TableQuest]:
    """
    앉은 사람에게 보일 퀘스트들. 판의 순서로 놓는다.

    숨긴 것은 아무에게도(방장에게도) 보이지 않는다. 있는지조차 알리지 않는다.
    """
    shown = [quest for quest in table.quests if quest.status != QuestStatus.HIDDEN]
    return in_catalog_order(shown, quests)
