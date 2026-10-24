# chat-server/app/world/proposals.py

"""
모델이 제안한 상태의 변화를 받아들이는 규칙(#676). DB 를 모르는 순수 함수다.

모델은 제안만 한다(conversation_core/changes.py). 지금 할 수 있는 것(Offer)을 서버가 정하고, 모델에게도 그것만 알린다.
받아들일 때도 같은 Offer 로 본다. 안 되는 것은 버린다(rejected 에 적고 부르는 쪽이 로그로 남긴다).
  - 호감도: 판에 호감도가 있고 model_step 이 0 보다 크면 된다. 크기는 ±model_step 으로 자르고 0~100 안으로 자른다
  - 선물: 판의 물건 가운데 상대가 줄 수 있는 것(giftable)이고 이 가지에서 아직 받지 않은 것이면 된다.
    소지품에 하나 더한다
    (같은 물건은 한 가지에서 한 번만. 아니면 모델이 답마다 같은 물건을 줄 수 있다)
  - 이동: 지금 있는 곳과 길로 바로 이어진 곳이면 된다. 사용자의 이동과 같다(시간이 흐르고, 가 본 곳, 호감도의 규칙)
한 답에 셋이 다 올 수 있다. 선물, 이동, 호감도의 차례로 적용한다. 할 수 있는 것은 답을 쓰기 전의 상태로 정한다.
받아들인 것은 칩(changes)으로 답에 붙는다. 단계 이름으로 보이는 캐릭터면 호감도의 크기를 싣지 않는다(오르내림만).
모델의 이동으로는 이벤트 씬이 나오지 않는다(답을 이미 썼다. 장면을 붙일 답이 없다).
"""

from dataclasses import dataclass, replace

from conversation_core.changes import Choice, Proposed, instruction

from app.assets.schemas import CharacterDocument, ItemDocument, PlaceDocument
from app.world.affection import REACH_PLACE, apply_affection, clamp
from app.world.items import add_one
from app.world.moves import apply_move, find_place
from app.world.state import WorldState

# 칩의 종류
AFFECTION = 'affection'
GIFT = 'gift'
MOVE = 'move'
# 숫자와 게이지로 보이는 호감도(asset 서버의 AffectionDisplay.NUMBER)
NUMBER_DISPLAY = 'number'


@dataclass(frozen=True)
class Reachable:
    """지금 있는 곳에서 길로 바로 갈 수 있는 장소 하나와 걸리는 시간(분)."""

    place: PlaceDocument
    minutes: int


@dataclass(frozen=True)
class Offer:
    """지금 모델이 제안할 수 있는 것. step 은 호감도를 바꿀 수 있는 크기(0 이면 못 바꾼다)다."""

    step: int
    gifts: tuple[ItemDocument, ...]
    routes: tuple[Reachable, ...]


@dataclass(frozen=True)
class Applied:
    """받아들인 뒤의 상태와 칩들. rejected 는 버린 제안의 종류다(로그에 남긴다)."""

    state: WorldState
    changes: tuple[dict, ...] = ()
    rejected: tuple[str, ...] = ()


def affection_step(document: CharacterDocument, state: WorldState) -> int:
    """모델이 바꿀 수 있는 호감도의 크기. 판에 호감도가 없으면 0 이다."""
    if document.affection is None or state.affection is None:
        return 0
    return max(document.affection.model_step, 0)


def gift_choices(document: CharacterDocument, state: WorldState) -> tuple[ItemDocument, ...]:
    """상대가 줄 수 있는 물건 가운데 이 가지에서 아직 받지 않은 것들(판의 차례)."""
    return tuple(item for item in document.items if item.giftable and item.id not in state.received)


def route_choices(document: CharacterDocument, state: WorldState) -> tuple[Reachable, ...]:
    """지금 있는 곳에서 길로 바로 갈 수 있는 장소들(판의 길의 차례, 같은 곳은 처음 길만). 지도가 없으면 없다."""
    if state.place is None:
        return ()
    routes: dict[str, Reachable] = {}
    for path in document.paths:
        if state.place not in (path.a, path.b):
            continue
        other = path.b if path.a == state.place else path.a
        place = find_place(document, other)
        if place is not None and other != state.place and other not in routes:
            routes[other] = Reachable(place, path.minutes)
    return tuple(routes.values())


def offer_of(document: CharacterDocument, state: WorldState) -> Offer:
    """지금 모델이 제안할 수 있는 것."""
    return Offer(affection_step(document, state), gift_choices(document, state), route_choices(document, state))


def render_offer(offer: Offer) -> str | None:
    """카드에 넣는 지시. 할 수 있는 것이 없으면 None."""
    gifts = [Choice(item.id, item.name) for item in offer.gifts]
    routes = [Choice(route.place.id, route.place.name) for route in offer.routes]
    return instruction(offer.step, gifts, routes)


def rejected(applied: Applied, kind: str) -> Applied:
    """버린 제안을 적는다."""
    return replace(applied, rejected=(*applied.rejected, kind))


def with_gift(offer: Offer, applied: Applied, item_id: str | None) -> Applied:
    """선물을 받아들인다. 줄 수 있는 것이 아니면 버린다."""
    if item_id is None:
        return applied
    if item_id not in {item.id for item in offer.gifts}:
        return rejected(applied, GIFT)
    state = add_one(applied.state, item_id)
    state = replace(state, received=(*state.received, item_id))
    return replace(applied, state=state, changes=(*applied.changes, {'kind': GIFT, 'item': item_id}))


def with_move(document: CharacterDocument, offer: Offer, applied: Applied, place_id: str | None) -> Applied:
    """이동을 받아들인다. 길로 바로 이어진 곳이 아니면 버린다. 사용자의 이동과 같이 호감도의 규칙을 건다."""
    if place_id is None:
        return applied
    route = next((route for route in offer.routes if route.place.id == place_id), None)
    if route is None:
        return rejected(applied, MOVE)
    moved = apply_affection(document, apply_move(applied.state, place_id, route.minutes), REACH_PLACE, place_id)
    change = {'kind': MOVE, 'place': place_id, 'minutes': route.minutes}
    return replace(applied, state=moved, changes=(*applied.changes, change))


def affection_change(document: CharacterDocument, before: int, after: int) -> dict:
    """호감도의 칩. 단계 이름으로 보이는 캐릭터면 크기를 싣지 않는다(화면의 코드로 숨기지 않는다)."""
    visible = document.affection is not None and document.affection.display == NUMBER_DISPLAY
    return {'kind': AFFECTION, 'rising': after > before, 'delta': after - before if visible else None}


def with_affection(document: CharacterDocument, offer: Offer, applied: Applied, delta: int | None) -> Applied:
    """호감도의 변화를 받아들인다. ±step 으로 자르고 0~100 안으로 자른다. 바꿀 수 없으면 버린다. 그대로면 칩이 없다."""
    if delta is None:
        return applied
    before = applied.state.affection
    if offer.step == 0 or before is None:
        return rejected(applied, AFFECTION)
    after = clamp(before + max(-offer.step, min(offer.step, delta)))
    if after == before:
        return applied
    state = replace(applied.state, affection=after)
    return replace(applied, state=state, changes=(*applied.changes, affection_change(document, before, after)))


def apply_proposals(document: CharacterDocument, state: WorldState, proposed: Proposed) -> Applied:
    """제안들을 받아들인 뒤의 상태와 칩들. 할 수 있는 것은 state(답을 쓰기 전의 상태)로 정한다."""
    offer = offer_of(document, state)
    applied = with_gift(offer, Applied(state), proposed.gift)
    applied = with_move(document, offer, applied, proposed.move)
    return with_affection(document, offer, applied, proposed.affection)
