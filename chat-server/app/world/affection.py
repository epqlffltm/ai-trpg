# chat-server/app/world/affection.py

"""
호감도의 규칙. DB 를 모르는 순수 함수다.

값은 0~100 하나다(판의 호감도가 없으면 None). 사용자의 행동(물건을 건넸다, 장소에 갔다, 물건을 썼다)에
제작자가 적은 규칙대로 엔진이 바꾼다. 대화의 내용으로는 모델의 제안(app/world/proposals.py)을 거쳐서만 움직인다.
  - 규칙은 (종류, 대상)이 그 행동과 같은 것이 모두 걸린다. 차례대로 더하고 0~100 안으로 자른다
  - 처음 한 번만(once)인 규칙은 그 가지에서 걸린 적이 있으면 건너뛴다. 걸린 것은 상태의 fired 에 적는다
단계는 값이 그 경계(at) 이상인 마지막 단계다. 모델에는 단계 이름만 간다.
"""

from dataclasses import replace

from app.assets.schemas import AffectionDocument, CharacterDocument, StageDocument
from app.world.state import WorldState

# 값의 범위
AFFECTION_MIN = 0
AFFECTION_MAX = 100
# 행동의 종류(asset 서버의 TriggerKind)
GIVE_ITEM = 'give_item'
REACH_PLACE = 'reach_place'
USE_ITEM = 'use_item'


def clamp(value: int) -> int:
    """0~100 안으로 자른다."""
    return max(AFFECTION_MIN, min(AFFECTION_MAX, value))


def apply_affection(document: CharacterDocument, state: WorldState, kind: str, target: str) -> WorldState:
    """그 행동(kind, target)으로 바뀐 호감도. 판에 호감도가 없거나 맞는 규칙이 없으면 그대로다."""
    if document.affection is None or state.affection is None:
        return state
    value, fired = state.affection, list(state.fired)
    for rule in document.affection.rules:
        if (rule.on.kind, rule.on.target) != (kind, target) or (rule.once and rule.id in fired):
            continue
        value = clamp(value + rule.change)
        if rule.once:
            fired.append(rule.id)
    return replace(state, affection=value, fired=tuple(fired))


def stage_index(affection: AffectionDocument, value: int) -> int:
    """값이 든 단계의 자리(0 부터). 경계가 값 이하인 마지막 단계다."""
    index = 0
    for position, stage in enumerate(affection.stages):
        if stage.at <= value:
            index = position
    return index


def stage_of(affection: AffectionDocument, value: int) -> StageDocument:
    """값이 든 단계."""
    return affection.stages[stage_index(affection, value)]
