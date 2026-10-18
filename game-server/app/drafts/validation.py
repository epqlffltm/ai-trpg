# game-server/app/drafts/validation.py

"""
모델의 초안을 테이블의 지금 상태에 대어 본다. 받을 것과 버릴 것을 가른다.

모델의 답은 모양이 맞아도 틀릴 수 있다(hallucination). 그래서 하나하나 서버의 규칙으로 다시 본다.
  - 이름표가 목록에 있는가. 없는 캐릭터, 없는 물건, 없는 퀘스트를 지어냈으면 버린다.
  - 퀘스트는 그 상태로 바꿀 수 있는가. 방장이 바꿀 때와 같은 규칙이다(app/tables/quests.py 의 change_problem).
    실패만 된다. 드러내기와 성공은 엔진의 몫이라 그 까닭(quest_reveal_by_engine, quest_success_by_engine)으로 버린다.
  - 같은 것을 두 번 적었으면 뒤의 것을 버린다.
버린 것은 까닭과 함께 남긴다. 모델이 얼마나 틀리는지 재는 근거다.

받은 것도 아직 초안이다. 상태를 바꾸지 않는다. 방장이 받아들일 때 바꾼다.
그때 다시 본다. 초안을 쓴 뒤에 캐릭터가 죽거나 퀘스트가 끝났을 수 있다.
"""

import uuid
from dataclasses import dataclass, field

from app.drafts.context import DraftContext
from app.drafts.output import DraftOutput, FoundItem, QuestChange
from app.tables import quests
from app.tables.models import QuestStatus


class Reason:
    """초안을 버린 까닭."""

    UNKNOWN_CHARACTER = 'unknown_character'
    UNKNOWN_ITEM = 'unknown_item'
    UNKNOWN_QUEST = 'unknown_quest'
    DUPLICATE = 'duplicate'


@dataclass(frozen=True)
class ItemDraft:
    """받은 초안: 캐릭터 하나가 물건 하나를 count 개 손에 넣었다."""

    user_id: uuid.UUID
    character_name: str
    entry_id: uuid.UUID
    name: str
    count: int


@dataclass(frozen=True)
class QuestDraft:
    """받은 초안: 퀘스트 하나가 previous 에서 status 가 됐다."""

    entry_id: uuid.UUID
    name: str
    previous: QuestStatus
    status: QuestStatus


@dataclass(frozen=True)
class Rejected:
    """버린 초안 하나. kind 는 found_item 또는 quest_change, reason 은 까닭이다."""

    kind: str
    reason: str


@dataclass(frozen=True)
class Checked:
    """대어 본 결과. 받은 것과 버린 것."""

    items: list[ItemDraft] = field(default_factory=list)
    quests: list[QuestDraft] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)


# 초안에 적을 거리가 없었거나 답을 쓰지 못했을 때의 결과
NOTHING = Checked()


def check_item(found: FoundItem, context: DraftContext) -> ItemDraft | str:
    """물건 초안 하나를 본다. 받으면 ItemDraft, 버리면 그 까닭."""
    character = context.characters.get(found.character)
    if character is None:
        return Reason.UNKNOWN_CHARACTER
    item = context.items.get(found.item)
    if item is None:
        return Reason.UNKNOWN_ITEM
    return ItemDraft(character.user_id, character.name, item.entry_id, item.name, found.count)


def check_quest(change: QuestChange, context: DraftContext) -> QuestDraft | str:
    """퀘스트 초안 하나를 본다. 받으면 QuestDraft, 버리면 그 까닭(바꿀 수 없으면 그 충돌의 이름)."""
    quest = context.quests.get(change.quest)
    if quest is None:
        return Reason.UNKNOWN_QUEST
    status = QuestStatus(change.status)
    problem = quests.change_problem(quest.status, status)
    if problem is not None:
        return problem
    return QuestDraft(quest.entry_id, quest.name, quest.status, status)


def check_items(output: DraftOutput, context: DraftContext) -> tuple[list[ItemDraft], list[Rejected]]:
    """물건 초안들을 본다. 같은 캐릭터의 같은 물건을 두 번 적었으면 뒤의 것을 버린다."""
    accepted, rejected, seen = [], [], set()
    for found in output.found_items:
        result = check_item(found, context)
        if isinstance(result, ItemDraft) and (result.user_id, result.entry_id) in seen:
            result = Reason.DUPLICATE
        if isinstance(result, str):
            rejected.append(Rejected('found_item', result))
            continue
        seen.add((result.user_id, result.entry_id))
        accepted.append(result)
    return accepted, rejected


def check_quests(output: DraftOutput, context: DraftContext) -> tuple[list[QuestDraft], list[Rejected]]:
    """퀘스트 초안들을 본다. 같은 퀘스트를 두 번 적었으면 뒤의 것을 버린다."""
    accepted, rejected, seen = [], [], set()
    for change in output.quest_changes:
        result = check_quest(change, context)
        if isinstance(result, QuestDraft) and result.entry_id in seen:
            result = Reason.DUPLICATE
        if isinstance(result, str):
            rejected.append(Rejected('quest_change', result))
            continue
        seen.add(result.entry_id)
        accepted.append(result)
    return accepted, rejected


def check_output(output: DraftOutput, context: DraftContext) -> Checked:
    """모델의 답 전체를 본다."""
    found_items, item_rejections = check_items(output, context)
    quest_changes, quest_rejections = check_quests(output, context)
    return Checked(items=found_items, quests=quest_changes, rejected=[*item_rejections, *quest_rejections])
