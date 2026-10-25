# story-server/app/turns/states.py

"""
엔진의 상태(app/engine/state.py 의 StoryState)를 말에 붙여 저장하는 모양(JSON)으로 바꾸고 되돌린다.
DB 도 모델도 모른다. 표(message_states)는 app/conversations/models.py 에 있다.

상태는 상태가 바뀐 말에만 붙는다(행동 말, 이벤트가 열린 말). 가지의 어느 말의 상태는 그 말부터 뿌리 쪽으로
처음 만나는 상태다. 하나도 없으면 판으로 만든 처음의 상태다(state_on_path). 다시 생성이나 앞 가지로 돌아가면
그 가지의 상태가 된다.

JSON 의 칸은 상태의 칸과 같은 이름이다. 모르는 칸은 버리고 없는 칸은 처음의 값이다.
상태에 칸이 늘어도 이미 저장한 상태를 그대로 읽는다.
"""

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from app.engine.state import StoryState, start_state
from app.engine.world import World


def state_to_json(state: StoryState) -> dict:
    """상태를 저장하는 모양으로. 차례가 없는 것(gifts, seen)은 정렬해 늘 같은 글이 되게 한다."""
    return {
        'minutes': state.minutes,
        'place': state.place,
        'items': dict(state.items),
        'affection': dict(state.affection),
        'gifts': sorted([cast_id, item] for cast_id, item in state.gifts),
        'seen': sorted(state.seen),
        'companions': list(state.companions),
        'choosing': state.choosing,
        'cooldowns': dict(state.cooldowns),
        'ending': state.ending,
    }


def counts(value: object) -> MappingProxyType[str, int]:
    """이름 → 수의 칸을 읽는다. 모양이 틀린 줄은 버린다."""
    if not isinstance(value, Mapping):
        return MappingProxyType({})
    return MappingProxyType({str(key): int(number) for key, number in value.items() if isinstance(number, int)})


def state_from_json(data: Mapping) -> StoryState:
    """저장한 모양을 상태로. 시각과 장소는 반드시 있다(저장할 때 늘 적는다)."""
    return StoryState(
        minutes=int(data['minutes']),
        place=str(data['place']),
        items=counts(data.get('items')),
        affection=counts(data.get('affection')),
        gifts=frozenset((str(pair[0]), str(pair[1])) for pair in data.get('gifts', ()) if len(pair) == 2),
        seen=frozenset(str(event_id) for event_id in data.get('seen', ())),
        companions=tuple(str(cast_id) for cast_id in data.get('companions', ())),
        choosing=data.get('choosing'),
        cooldowns=counts(data.get('cooldowns')),
        ending=data.get('ending'),
    )


def state_on_path(world: World, path_states: Sequence[Mapping | None]) -> StoryState:
    """
    가지의 끝의 상태. path_states 는 가지의 말들(첫 말부터)에 붙은 상태다(없으면 None).
    끝에서 가장 가까운 것을 쓴다. 하나도 없으면 처음의 상태다.
    """
    for data in reversed(path_states):
        if data is not None:
            return state_from_json(data)
    return start_state(world)
