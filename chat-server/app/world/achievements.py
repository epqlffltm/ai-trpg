# chat-server/app/world/achievements.py

"""
업적을 준다(docs/architecture/achievements.md 의 "chat"). 판과 상태, 보낸 말의 수만 보는 순수한 함수다. DB 를 모른다.

업적은 제작자가 작품에 단 것이다(스팀의 업적과 같다). 인증 서버의 활동 배지와는 다른 것이다.
  - 답을 저장한 뒤의 가지로 본다. 행동, 모델이 제안해 받아들인 상태의 변화, 보낸 말의 수가 모두 들어 있다
  - 조건의 종류는 엔진이 이미 아는 것뿐이다
    (가 본 장소, 가진 물건, 받은 물건, 호감도의 단계, 나온 이벤트 씬, 보낸 말의 수).
    대화의 내용은 보지 않는다. 모르는 종류는 맞지 않는다
  - 조건이 비면 주지 않는다(늘 맞으면 첫 답에 그냥 받는다). 모두(all) 또는 하나라도(any)다
  - 계정마다 한 번이다. 이미 받은 것(owned)은 다시 주지 않는다. 받은 차례는 판의 차례다
"""

from collections.abc import Callable

from app.assets.schemas import AchievementConditionDocument, AchievementDocument, CharacterDocument
from app.world.scenes import stage_reached
from app.world.state import WorldState


def held(state: WorldState, item: str | None) -> int:
    """그 물건을 가진 수."""
    return sum(holding.count for holding in state.inventory if holding.item == item)


# 조건의 종류마다 맞추는 법. (판, 상태, 보낸 말의 수, 조건) → 맞는가
CHECKS: dict[str, Callable[[CharacterDocument, WorldState, int, AchievementConditionDocument], bool]] = {
    'visited_place': lambda document, state, sent, item: item.target in state.visited,
    'hold_item': lambda document, state, sent, item: held(state, item.target) >= item.count,
    'received_item': lambda document, state, sent, item: item.target in state.received,
    'affection_stage': lambda document, state, sent, item: stage_reached(document, state, item.value or ''),
    'scene_seen': lambda document, state, sent, item: item.target in state.shown,
    'messages_at_least': lambda document, state, sent, item: sent >= item.count,
}


def is_met(document: CharacterDocument, state: WorldState, sent: int, item: AchievementConditionDocument) -> bool:
    """조건 하나가 맞는가. 모르는 종류는 아니다."""
    check = CHECKS.get(item.kind)
    return check is not None and check(document, state, sent, item)


def is_earned(document: CharacterDocument, state: WorldState, sent: int, achievement: AchievementDocument) -> bool:
    """그 업적의 조건이 맞는가. 조건이 없으면 아니다."""
    items = achievement.when.items
    if not items:
        return False
    met = (is_met(document, state, sent, item) for item in items)
    return any(met) if achievement.when.match == 'any' else all(met)


def newly_earned(
    document: CharacterDocument, state: WorldState, sent: int, owned: frozenset[str]
) -> tuple[AchievementDocument, ...]:
    """아직 받지 않은 업적 가운데 지금 조건이 맞는 것들. 판의 차례다."""
    return tuple(
        achievement
        for achievement in document.achievements
        if achievement.id not in owned and is_earned(document, state, sent, achievement)
    )
