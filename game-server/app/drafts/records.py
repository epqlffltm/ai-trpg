# game-server/app/drafts/records.py

"""
검증을 거친 초안(app/drafts/validation.py)을 장부 초안의 줄(LedgerDraft)로 바꾼다. 순수 함수다.

버린 초안은 줄로 남기지 않는다. 그것은 호출 기록(모델이 쓴 글)에 남아 있다.
"""

import uuid

from app.drafts.models import DraftKind, LedgerDraft
from app.drafts.validation import Checked, ItemDraft, QuestDraft


def item_payload(item: ItemDraft) -> dict:
    """물건 초안 하나의 내용."""
    return {
        'user_id': str(item.user_id),
        'character_name': item.character_name,
        'entry_id': str(item.entry_id),
        'name': item.name,
        'count': item.count,
    }


def quest_payload(quest: QuestDraft) -> dict:
    """퀘스트 초안 하나의 내용."""
    return {'entry_id': str(quest.entry_id), 'name': quest.name, 'previous': quest.previous, 'status': quest.status}


def to_rows(table_id: uuid.UUID, round_number: int, checked: Checked) -> list[LedgerDraft]:
    """받은 초안들을 줄로. 물건이 먼저, 그다음 퀘스트다. 모델이 쓴 순서를 지킨다(position)."""
    contents = [(DraftKind.FOUND_ITEM, item_payload(item)) for item in checked.items]
    contents += [(DraftKind.QUEST_CHANGE, quest_payload(quest)) for quest in checked.quests]
    return [
        LedgerDraft(table_id=table_id, round_number=round_number, position=position, kind=kind, payload=payload)
        for position, (kind, payload) in enumerate(contents)
    ]
