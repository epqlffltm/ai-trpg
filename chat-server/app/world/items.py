# chat-server/app/world/items.py

"""
물건을 쓰고 건네는 규칙. DB 를 모르는 순수 함수다(check_held, apply_use, apply_give).

사용자가 소지품에서 물건을 고르면 서버가 가지고 있는지 보고, 되면 상태를 바꾼다. 모델은 바뀐 상태를 받아 반응만 쓴다.
  - 쓰기: 쓰면 없어지는 물건(consumable)이면 하나 줄고, 아니면 그대로다(2026-10-22 유저 결정, 물건마다 정한다)
  - 건네기: 하나 줄고 상대에게 간다. 옷이면 상대의 차림에 들어간다(이미 입은 옷이면 그대로)
수가 0 이 되면 소지품에서 뺀다.
"""

from dataclasses import replace

from app.assets.schemas import CharacterDocument, ItemDocument
from app.world.refusals import ActionRefusedError, Refusal
from app.world.state import Holding, WorldState

# 옷의 종류(asset 서버의 ItemKind.CLOTHING)
CLOTHING = 'clothing'


def find_item(document: CharacterDocument, item_id: str) -> ItemDocument | None:
    """판의 물건 하나. 없으면 None."""
    return next((item for item in document.items if item.id == item_id), None)


def held_count(state: WorldState, item_id: str) -> int:
    """그 물건을 몇 개 가졌나."""
    return sum(holding.count for holding in state.inventory if holding.item == item_id)


def check_held(document: CharacterDocument, state: WorldState, item_id: str) -> ItemDocument:
    """쓰거나 건넬 수 있는 물건. 판에 없으면 item_not_found, 가지고 있지 않으면 not_held(ActionRefusedError)."""
    item = find_item(document, item_id)
    if item is None:
        raise ActionRefusedError(Refusal.ITEM_NOT_FOUND)
    if held_count(state, item_id) < 1:
        raise ActionRefusedError(Refusal.NOT_HELD)
    return item


def take_one(state: WorldState, item_id: str) -> WorldState:
    """소지품에서 그 물건을 하나 뺀다. 0 이 되면 줄을 지운다."""
    inventory = tuple(
        Holding(holding.item, holding.count - 1) if holding.item == item_id else holding for holding in state.inventory
    )
    return replace(state, inventory=tuple(holding for holding in inventory if holding.count > 0))


def add_one(state: WorldState, item_id: str) -> WorldState:
    """소지품에 그 물건을 하나 더한다. 없던 물건이면 줄을 끝에 더한다."""
    if held_count(state, item_id) == 0:
        return replace(state, inventory=(*state.inventory, Holding(item_id, 1)))
    inventory = tuple(
        Holding(holding.item, holding.count + 1) if holding.item == item_id else holding for holding in state.inventory
    )
    return replace(state, inventory=inventory)


def apply_use(state: WorldState, item: ItemDocument) -> WorldState:
    """쓴 뒤의 상태. 쓰면 없어지는 물건이면 하나 준다. 검사는 check_held 가 한다."""
    return take_one(state, item.id) if item.consumable else state


def apply_give(state: WorldState, item: ItemDocument) -> WorldState:
    """건넨 뒤의 상태. 하나 줄고, 옷이면 상대의 차림에 들어간다. 검사는 check_held 가 한다."""
    given = take_one(state, item.id)
    if item.kind != CLOTHING or item.id in given.outfit:
        return given
    return replace(given, outfit=(*given.outfit, item.id))


def object_particle(word: str) -> str:
    """목적격 조사. 받침이 있으면 '을', 없으면 '를'. 한글로 끝나지 않으면 '을(를)'."""
    last = word[-1:] or ' '
    if not '가' <= last <= '힣':
        return '을(를)'
    return '을' if (ord(last) - ord('가')) % 28 else '를'


def use_text(item: ItemDocument) -> str:
    """쓴 행동 말의 글."""
    return f'{item.name}{object_particle(item.name)} 썼다.'


def give_text(item: ItemDocument) -> str:
    """건넨 행동 말의 글."""
    return f'{item.name}{object_particle(item.name)} 건넸다.'
