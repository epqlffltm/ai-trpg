# trpg-server/app/rounds/monster_scene.py

"""
이번 장면의 몬스터. 앉은 사람이 행동으로 겨눌 수 있는 마리와, 그 마리를 부르는 이름과 몸 상태.

장면의 몬스터는 글이 아니라 자리로 정한다. NPC 는 장면의 글에 이름이 나왔는지로 고르지만(app/rounds/cast.py),
몬스터는 "수로 쥐 2"처럼 번호로 부르므로 글에서 찾기 어렵고, 서술이 빠뜨리면 거기 있는 몬스터를 칠 수 없게 된다.
그래서 살아 있는 캐릭터가 서 있는 장소들의 마리를 모두 든다(쓰러짐, 죽음 포함). 일행이 아는 것은 함께 안다.
아무도 서 있지 않은 장소의 몬스터는 들지 않는다. 아직 가 보지 않은 곳에 무엇이 있는지 드러나면 안 된다.

겨눌 수 있는 것은 자기가 선 장소의 죽지 않은 마리뿐이다. 받을 때(app/rounds/acceptance.py)와
판정할 때(app/rounds/checks.py) 두 번 본다. 차례가 오기 전에 앞사람이 죽였을 수 있다.

여기의 함수는 DB 를 모른다. 이미 읽어 온 판, 테이블, 몬스터 상태를 받는다.
"""

import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from app.assets.scenarios.snapshot import MonsterSnapshot, Snapshot
from app.rounds.cast import condition_of
from app.tables import monsters as table_monsters
from app.tables import sheets
from app.tables.models import GameTable, TableMember, TableMonster


class Gone:
    """판정할 때 겨눈 마리를 칠 수 없는 까닭. 결과의 target_gone.reason 에 적는다."""

    # 차례가 오기 전에 죽었다(앞사람이 죽였다)
    DEAD = 'dead'
    # 행동한 캐릭터와 다른 장소에 있다
    ELSEWHERE = 'elsewhere'


@dataclass(frozen=True)
class SceneMonster:
    """이번 장면의 몬스터 한 마리. 테이블의 상태와, 판의 몬스터(글, 타입, 숫자)와, 부르는 이름이다."""

    state: TableMonster
    definition: MonsterSnapshot
    name: str


def occupied_places(table: GameTable) -> set[uuid.UUID]:
    """살아 있는 캐릭터가 서 있는 장소들. 쓰러진 캐릭터도 그 자리에 있다. 죽은 캐릭터와 맵에 없는 캐릭터는 뺀다."""
    return {
        member.sheet.place_id
        for member in table.members
        if member.sheet is not None and member.sheet.place_id is not None and not sheets.is_dead(member)
    }


def label_of(state: TableMonster, definition: MonsterSnapshot, counts: Counter[uuid.UUID]) -> str:
    """
    이 마리를 부르는 이름. 같은 몬스터가 테이블에 둘 이상이면 이름 뒤에 번호를 붙인다(수로 쥐 2).

    네임드 몹은 판 전체에서 한 마리라 번호를 붙이지 않는다.
    """
    if not definition.unique and counts[state.monster_id] > 1:
        return f'{definition.name} {state.number}'
    return definition.name


def scene_monsters(snapshot: Snapshot, table: GameTable, states: Iterable[TableMonster]) -> list[SceneMonster]:
    """
    이번 장면의 몬스터들. 살아 있는 캐릭터가 서 있는 장소들의 마리다. 판의 몬스터 순서, 그 안의 번호 순서다.

    번호를 붙일지는 테이블 전체의 마릿수로 정한다. 장면에 한 마리만 보여도 다른 곳에 같은 것이 있으면 번호를 붙인다.
    그래야 같은 마리가 장면마다 다른 이름으로 불리지 않는다.
    """
    states = list(states)
    counts = Counter(state.monster_id for state in states)
    here = occupied_places(table)
    order = {monster.id: position for position, monster in enumerate(snapshot.monsters)}
    definitions = {monster.id: monster for monster in snapshot.monsters}
    present = sorted(
        (state for state in states if state.place_id in here),
        key=lambda state: (order[state.monster_id], state.number),
    )
    return [
        SceneMonster(
            state=state,
            definition=definitions[state.monster_id],
            name=label_of(state, definitions[state.monster_id], counts),
        )
        for state in present
    ]


def find_scene_monster(monsters: list[SceneMonster], monster_id: uuid.UUID) -> SceneMonster | None:
    """이번 장면의 몬스터 중에서 이 마리를 찾는다. 장면에 없으면 None."""
    return next((monster for monster in monsters if monster.state.id == monster_id), None)


def stands_with(member: TableMember, monster: SceneMonster) -> bool:
    """이 캐릭터가 이 마리와 같은 장소에 서 있는가."""
    return member.sheet is not None and member.sheet.place_id == monster.state.place_id


def gone_reason(member: TableMember, monster: SceneMonster) -> str | None:
    """판정할 때 이 마리를 칠 수 없으면 그 까닭. 칠 수 있으면 None."""
    if table_monsters.is_dead(monster.state):
        return Gone.DEAD
    if not stands_with(member, monster):
        return Gone.ELSEWHERE
    return None


def condition(monster: SceneMonster) -> str:
    """이 마리의 몸 상태를 말로. NPC 와 같은 말이다(멀쩡함, 다침, 크게 다침, 쓰러짐, 죽음)."""
    return condition_of(monster.state)
