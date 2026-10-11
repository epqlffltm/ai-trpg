# game-server/app/tables/npcs.py

"""
테이블의 NPC 상태(table_npcs)를 만들고 바꾸는 작은 함수들.

DB 를 모른다. 이미 읽어 온 판과 상태를 받아 객체를 만들거나 고친다. 저장은 부른 쪽이 한다.

만들기. 게임을 시작할 때 판의 인물 항목마다 상태를 하나씩 만든다(app/tables/service.py). 숫자는 판에서 온다.
그 인물의 NPC 시트가 있으면 그것, 없으면 기본 NPC 시트다(app/assets/scenarios/snapshot.py 의 npc_sheet_of).
HP 는 가득 찬 채로, 살아 있는 채로 시작한다.

바꾸기. NPC 의 HP 와 생사를 바꾸는 함수는 change_npc 하나다. 판정의 결과로 라운드가 부른다(app/rounds/service.py).
방장이 손으로 고치거나 되돌리는 길은 없다. 바뀐 것은 부른 쪽이 이벤트로 남긴다.
  - 피해와 회복의 양은 규칙의 등급으로 주사위를 굴려 정한다(app/engine/health.py). PC 와 같다.
  - HP 가 0 이 되면 제압은 쓰러뜨리고, 죽이려는 타격은 죽인다. 쓰러진 NPC 를 죽이려고 치면 죽는다.
  - 쓰러진 NPC 는 죽음의 굴림이 없다. 혼자서 깨어나지 못하고, 회복을 받으면 일어난다.
  - 죽은 NPC 는 바꾸지 않는다. 부르는 쪽이 먼저 걸러 낸다(is_dead).
"""

import uuid

from app.assets.scenarios.snapshot import Snapshot, npc_sheet_of, person_entries
from app.engine import health
from app.engine.dice import Dice
from app.engine.health import Change, ChangeKind
from app.engine.ruleset import Magnitude
from app.engine.sheet import Sheet
from app.tables.models import NpcStatus, TableNpc


def new_npc(table_id: uuid.UUID, entry_id: uuid.UUID, source: Sheet) -> TableNpc:
    """인물 하나의 상태를 만든다. 시트의 숫자를 복사하고, HP 를 가득 채우고, 살아 있는 것으로 둔다."""
    return TableNpc(
        table_id=table_id,
        entry_id=entry_id,
        abilities=dict(source.abilities),
        max_hp=source.max_hp,
        hp=source.max_hp,
        status=NpcStatus.ALIVE,
    )


def make_npcs(table_id: uuid.UUID, snapshot: Snapshot) -> list[TableNpc]:
    """이 테이블의 인물마다 상태를 만든다. 판의 인물 항목 순서다. 인물이 없으면 빈 목록이다."""
    return [new_npc(table_id, entry.id, npc_sheet_of(snapshot, entry.id)) for entry in person_entries(snapshot)]


def is_dead(npc: TableNpc) -> bool:
    """이 NPC 가 죽었는가. 죽은 NPC 는 겨누지 못하고, 바뀌지 않는다."""
    return npc.status == NpcStatus.DEAD


def status_after(hp: int, lethal: bool) -> NpcStatus:
    """
    HP 가 바뀐 뒤의 생사. HP 가 있으면 살아 있다. 0 이면 죽이려는 타격은 죽음, 아니면 쓰러짐이다.

    회복은 늘 HP 를 1 이상 올리므로 회복 뒤에는 살아 있다. 쓰러진 NPC 가 제압을 또 받으면 쓰러진 채다.
    """
    if not health.is_downed(hp):
        return NpcStatus.ALIVE
    return NpcStatus.DEAD if lethal else NpcStatus.DOWNED


def change_npc(npc: TableNpc, kind: ChangeKind, magnitude: Magnitude, lethal: bool, dice: Dice) -> Change:
    """
    NPC 의 HP 와 생사를 한 번 바꾼다. 양을 정하는 주사위를 여기서 굴린다. 바뀐 것을 돌려준다.

    NPC 의 상태를 고치는 길은 이 함수 하나다. 상태를 고친다. 저장하지는 않는다. 죽은 NPC 에는 부르지 않는다.
    lethal 은 피해가 죽이려는 것인지다. 회복에는 뜻이 없다. 회복 뒤에는 HP 가 있어서 늘 살아 있다(status_after).
    """
    change = health.change_hp(kind, magnitude, npc.hp, npc.max_hp, dice)
    npc.hp = change.after
    npc.status = status_after(change.after, lethal)
    return change
