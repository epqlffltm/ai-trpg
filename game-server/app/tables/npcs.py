# game-server/app/tables/npcs.py

"""
테이블의 NPC 상태(table_npcs)를 만드는 작은 함수들.

DB 를 모른다. 이미 읽어 온 판을 받아 객체를 만든다. 저장은 부른 쪽(app/tables/service.py)이 한다.

게임을 시작할 때 판의 인물 항목마다 상태를 하나씩 만든다. 숫자는 판에서 온다.
그 인물의 NPC 시트가 있으면 그것, 없으면 기본 NPC 시트다(app/assets/scenarios/snapshot.py 의 npc_sheet_of).
HP 는 가득 찬 채로, 살아 있는 채로 시작한다.
"""

import uuid

from app.assets.scenarios.snapshot import Snapshot, npc_sheet_of, person_entries
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
