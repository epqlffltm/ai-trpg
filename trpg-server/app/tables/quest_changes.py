# trpg-server/app/tables/quest_changes.py

"""
퀘스트가 바뀐 것을 이벤트(quest_changed)에 적을 모양.

퀘스트를 바꾸는 것은 엔진뿐이다. 드러내기, 성공, 실패는 판의 조건을 라운드가 닫힐 때 보고(app/rounds/quest_goals.py),
기한을 넘긴 것은 실패로 바꾼다(app/rounds/deadlines.py). 방장은 PC 라서 결과를 정하지 않는다(#367).
AI GM 은 퀘스트를 바꾸지 못한다. 서술에서 "왕녀를 구했다"고 해도 퀘스트는 그대로다.
"""

from app.calendar import clock
from app.tables.models import QuestStatus
from app.tables.quests import CatalogQuest


def due_at_document(minutes: int | None) -> dict | None:
    """기한이 끝나는 시각을 이벤트에 적을 모양(며칠째 몇 시). 기한이 없으면 None."""
    return None if minutes is None else clock.as_document(minutes)


def describe(
    quest: CatalogQuest,
    previous: str,
    status: QuestStatus,
    rewards: list[dict],
    due_at: int | None,
    reason: str | None = None,
    consumed: list[dict] | None = None,
) -> dict:
    """
    바꾼 것을 이벤트에 적을 모양. 무엇이, 무엇에서 무엇으로, 누가 무엇을 받았는가, 기한은 언제 끝나는가.

    reason 은 엔진이 바꾼 까닭이다. 조건이 채워짐(conditions_met, app/rounds/quest_goals.py),
    기한을 넘김(app/rounds/deadlines.py).
    consumed 는 이룬 퀘스트가 가져간 물건이다(app/rounds/quest_handover.py). 보상과 같은 모양이다. 없으면 빈 목록이다.
    """
    return {
        'entry_id': str(quest.entry_id),
        'name': quest.name,
        'previous': previous,
        'status': status,
        'rewards': rewards,
        'consumed': consumed or [],
        'due_at': due_at_document(due_at),
        'reason': reason,
    }
