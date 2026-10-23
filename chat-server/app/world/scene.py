# chat-server/app/world/scene.py

"""
모델에 보내는 "[지금]" 블록. 지금 있는 장소와 그 설명, 갈 수 있는 곳, 사용자의 소지품, 상대의 차림,
사용자에 대한 상대의 호감도(단계 이름만. 숫자는 보내지 않는다)다.
DB 를 모르는 순수 함수다.

모델은 이것을 읽고 반응만 쓴다. 바꾸는 것은 서버다(이동, 쓰기, 건네기).
지도와 물건이 없는 캐릭터면 블록이 없다. 판에 없는 id 는(있을 수 없지만) 빼고 적는다.
"""

from app.assets.schemas import CharacterDocument
from app.world.affection import stage_of
from app.world.moves import find_place
from app.world.state import WorldState


def place_line(document: CharacterDocument, state: WorldState) -> str | None:
    """'장소: 이름 — 설명'. 장소가 없으면 None."""
    place = find_place(document, state.place) if state.place else None
    if place is None:
        return None
    return f'장소: {place.name} — {place.description}' if place.description else f'장소: {place.name}'


def exits_line(document: CharacterDocument, state: WorldState) -> str | None:
    """'갈 수 있는 곳: 카페(15분), …'. 갈 곳이 없으면 None."""
    exits = []
    for path in document.paths:
        if state.place in (path.a, path.b):
            other = find_place(document, path.b if path.a == state.place else path.a)
            if other is not None:
                exits.append(f'{other.name}({path.minutes}분)')
    return f'갈 수 있는 곳: {", ".join(exits)}' if exits else None


def inventory_line(document: CharacterDocument, state: WorldState) -> str | None:
    """'사용자의 소지품: 시집 2개, …'. 가진 것이 없으면 None."""
    names = {item.id: item.name for item in document.items}
    held = [f'{names[holding.item]} {holding.count}개' for holding in state.inventory if holding.item in names]
    return f'사용자의 소지품: {", ".join(held)}' if held else None


def outfit_line(document: CharacterDocument, state: WorldState) -> str | None:
    """'상대의 차림: 목도리, …'. 사용자가 건넨 옷이 없으면 None."""
    names = {item.id: item.name for item in document.items}
    worn = [names[item] for item in state.outfit if item in names]
    return f'상대의 차림: {", ".join(worn)}' if worn else None


def affection_line(document: CharacterDocument, state: WorldState) -> str | None:
    """'사용자에 대한 호감: 친구'. 호감도가 없으면 None. 모델에는 단계 이름만 간다."""
    if document.affection is None or state.affection is None:
        return None
    return f'사용자에 대한 호감: {stage_of(document.affection, state.affection).name}'


def render_scene(document: CharacterDocument, state: WorldState) -> str | None:
    """'[지금]' 블록. 적을 것이 없으면 None."""
    found = (
        place_line(document, state),
        exits_line(document, state),
        inventory_line(document, state),
        outfit_line(document, state),
        affection_line(document, state),
    )
    lines = [line for line in found if line]
    return '\n'.join(['[지금]', *lines]) if lines else None
