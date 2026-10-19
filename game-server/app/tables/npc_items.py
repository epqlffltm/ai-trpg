# game-server/app/tables/npc_items.py

"""
NPC 하나가 지닌 물건(#457). 판의 NPC 시트에 적은 장비와 소지품을 테이블마다 센다.

세는 규칙은 몬스터와 같다(app/tables/carried.py). 바뀐 줄만 행(TableNpcItem)으로 적는다.
NPC 시트를 적지 않은 인물(기본 NPC 시트를 받는 인물)은 아무것도 지니지 않는다.
여기는 NPC 의 행을 읽고 만드는 것만 한다.

DB 를 모른다. 이미 읽어 온 NPC 의 상태(TableNpc)와 판의 NPC 시트(NpcSheetSnapshot)를 받아 개수를 읽고 고친다.
저장은 부르는 쪽이 한다.
"""

from app.assets.scenarios.snapshot import NpcSheetSnapshot
from app.tables import carried as carried_items
from app.tables.carried import Carried
from app.tables.models import TableNpc, TableNpcItem


def carried(npc: TableNpc, definition: NpcSheetSnapshot | None) -> list[Carried]:
    """그 인물이 지금 지닌 것. 줄의 차례다. 0 이 된 줄은 뺀다. 시트가 없으면(None) 빈 목록이다."""
    return carried_items.carried(npc.items, definition)


def set_count(npc: TableNpc, slot: int, count: int) -> None:
    """그 줄의 개수를 고친다. 처음 바뀌는 줄이면 행을 만든다."""
    row = carried_items.find_row(npc.items, slot)
    if row is None:
        npc.items.append(TableNpcItem(table_id=npc.table_id, entry_id=npc.entry_id, slot=slot, count=count))
        return
    row.count = count
