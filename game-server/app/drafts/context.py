# game-server/app/drafts/context.py

"""
초안을 쓰는 모델에게 보일 목록. 캐릭터, 물건, 퀘스트에 짧은 이름표(p1, i1, q1)를 붙인다.

모델은 이 목록 안에서만 고를 수 있다. 목록에 없는 것을 가리키면 서버가 버린다(app/drafts/validation.py).
목록은 테이블의 지금 상태에서 만든다. DB 를 모른다. 이미 읽은 테이블과 판을 받는다.

  - 캐릭터: 앉은 사람의 지금 캐릭터 중 살아 있는 것. 앉은 순서다. 죽은 캐릭터는 물건을 받지 않는다.
  - 물건: 판의 물건 전부. 판의 순서다.
  - 퀘스트: 진행 중인 것. 판의 순서다. 초안이 적을 수 있는 것은 진행 중인 퀘스트의 실패뿐이다.
    드러내기와 성공은 엔진이 정하고(app/rounds/quest_goals.py), 숨긴 것은 방장에게도 보이지 않는다.
    초안은 방장이 보므로 숨긴 퀘스트의 이름을 실을 수 없다. 끝난 것은 더 바뀌지 않는다.
"""

import uuid
from dataclasses import dataclass

from app.assets.scenarios.snapshot import Snapshot
from app.tables import items, quests, sheets
from app.tables.models import GameTable, QuestStatus


@dataclass(frozen=True)
class CharacterChoice:
    """고를 수 있는 캐릭터 하나. 누구의 캐릭터인가와 그 이름."""

    label: str
    user_id: uuid.UUID
    name: str


@dataclass(frozen=True)
class ItemChoice:
    """고를 수 있는 물건 하나. 판의 로어북 물건 항목이다."""

    label: str
    entry_id: uuid.UUID
    name: str


@dataclass(frozen=True)
class QuestChoice:
    """고를 수 있는 퀘스트 하나와 그 지금 상태."""

    label: str
    entry_id: uuid.UUID
    name: str
    status: QuestStatus


@dataclass(frozen=True)
class DraftContext:
    """모델에게 보일 목록 전부. 이름표로 찾는다."""

    characters: dict[str, CharacterChoice]
    items: dict[str, ItemChoice]
    quests: dict[str, QuestChoice]


def label_of(prefix: str, index: int) -> str:
    """이름표 하나. 앞 글자와 1 부터 세는 번호다. 예: p1"""
    return f'{prefix}{index + 1}'


def character_choices(table: GameTable) -> dict[str, CharacterChoice]:
    """살아 있는 지금 캐릭터들에 이름표를 붙인다. 앉은 순서다."""
    living = [member for member in table.members if member.sheet is not None and not sheets.is_dead(member)]
    return {
        label_of('p', index): CharacterChoice(label_of('p', index), member.user_id, member.character_name)
        for index, member in enumerate(living)
    }


def item_choices(snapshot: Snapshot) -> dict[str, ItemChoice]:
    """판의 물건들에 이름표를 붙인다. 판의 순서다."""
    return {
        label_of('i', index): ItemChoice(label_of('i', index), item.entry_id, item.name)
        for index, item in enumerate(items.catalog(snapshot).values())
    }


def quest_choices(table: GameTable, snapshot: Snapshot) -> dict[str, QuestChoice]:
    """진행 중인 퀘스트들에 이름표를 붙인다. 판의 순서다."""
    catalog = quests.catalog(snapshot)
    open_rows = [row for row in quests.in_catalog_order(table.quests, catalog) if row.status == QuestStatus.ACTIVE]
    return {
        label_of('q', index): QuestChoice(
            label_of('q', index), row.entry_id, catalog[row.entry_id].name, QuestStatus(row.status)
        )
        for index, row in enumerate(open_rows)
    }


def build_context(table: GameTable, snapshot: Snapshot) -> DraftContext:
    """테이블의 지금 상태에서 모델에게 보일 목록을 만든다."""
    return DraftContext(
        characters=character_choices(table), items=item_choices(snapshot), quests=quest_choices(table, snapshot)
    )


def has_choices(context: DraftContext) -> bool:
    """초안에 적을 거리가 있는가. 받을 캐릭터와 물건이 함께 있거나, 진행 중인 퀘스트가 있어야 한다."""
    return bool(context.characters and context.items) or bool(context.quests)
