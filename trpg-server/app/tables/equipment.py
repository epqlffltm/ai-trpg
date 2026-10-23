# trpg-server/app/tables/equipment.py

"""
캐릭터가 착용한 장비를 다루는 규칙(#276). 무엇을 어느 칸에 끼우고, 언제 빠지는가.

  - 칸은 규칙이 정한다(Ruleset.equipment_slots). 칸마다 물건 하나다.
  - 물건은 들어갈 수 있는 칸과 차지하는 칸의 수를 판의 아이템 규칙에 적는다. 두 손 검은 주손과 보조손을 함께 차지한다.
  - 착용한 물건은 소지품의 일부다. 가진 개수보다 많이 착용하지 않는다. 소지품이 줄면(건네기, 팔기, 내려놓기 …)
    착용하지 않은 것부터 나가고, 가진 것보다 착용한 것이 많아지면 그만큼 벗는다(trim).
  - 이미 찬 칸에 끼우면 그 칸의 것을 벗기고 끼운다. 가진 것이 모두 착용 중이면 하나를 옮긴다.
  - 시작할 때 판에 적은 대로 끼운다(dress). 새 캐릭터도 같다.

DB 를 모른다. 이미 읽어 온 시트의 착용(TableWorn)을 고친다. 저장은 부르는 쪽이 한다.
소지품의 개수는 부르는 쪽이 넘긴다. 이 파일은 소지품(app/tables/items.py)을 가져오지 않는다. 소지품이 이 파일을 부른다.
"""

import uuid
from collections.abc import Sequence

from app.assets.scenarios.snapshot import ItemStackSnapshot, Snapshot
from app.engine.ruleset import Ruleset
from app.tables.errors import TableOptionError
from app.tables.models import TableSheet, TableWorn


def worn_of(sheet: TableSheet, entry_id: uuid.UUID) -> list[TableWorn]:
    """이 캐릭터가 그 물건을 착용한 것들. 끼운 차례다."""
    return [row for row in sheet.worn if row.entry_id == entry_id]


def occupying(sheet: TableSheet, slots: Sequence[str]) -> list[TableWorn]:
    """그 칸들 중 하나라도 차지한 착용들. 끼운 차례다."""
    return [row for row in sheet.worn if set(row.slots) & set(slots)]


def require_fits(ruleset: Ruleset, slots_of_item: Sequence[str], slot_count: int, slots: Sequence[str]) -> None:
    """
    그 물건을 그 칸들에 끼울 수 있는지 본다. 아니면 TableOptionError.

    착용하지 않는 물건(칸이 없다)이면 entry_id, 칸이 규칙에 없거나 그 물건의 칸이 아니거나 수가 맞지 않거나
    같은 칸을 두 번 적었으면 slots 다.
    """
    if not slots_of_item:
        raise TableOptionError('entry_id')
    rule_slots = {slot.key for slot in ruleset.equipment_slots}
    if len(slots) != slot_count or len(set(slots)) != len(slots):
        raise TableOptionError('slots')
    if any(slot not in slots_of_item or slot not in rule_slots for slot in slots):
        raise TableOptionError('slots')


def wear(
    table_id: uuid.UUID, sheet: TableSheet, entry_id: uuid.UUID, slots: Sequence[str], held: int
) -> list[TableWorn]:
    """
    그 물건 하나를 그 칸들에 끼운다. 벗겨진 착용들을 돌려준다.

    그 칸들을 차지한 것을 먼저 벗긴다. 가진 것(held)이 모두 착용 중이면 가장 먼저 끼운 하나를 옮긴다.
    held 는 그 물건을 가진 개수다. 하나 이상일 때만 부른다. 칸은 require_fits 로 본 것이다.
    """
    removed = occupying(sheet, slots)
    for row in removed:
        sheet.worn.remove(row)
    still_worn = worn_of(sheet, entry_id)
    if len(still_worn) >= held:
        moved = still_worn[0]
        sheet.worn.remove(moved)
        removed.append(moved)
    sheet.worn.append(TableWorn(table_id=table_id, entry_id=entry_id, slots=list(slots)))
    return removed


def take_off(sheet: TableSheet, slot: str) -> TableWorn | None:
    """그 칸을 차지한 착용을 벗긴다. 벗긴 것을 돌려준다. 비어 있으면 아무것도 하지 않고 None."""
    row = next(iter(occupying(sheet, [slot])), None)
    if row is not None:
        sheet.worn.remove(row)
    return row


def trim(sheet: TableSheet, entry_id: uuid.UUID, held: int) -> None:
    """
    가진 개수(held)보다 많이 착용했으면 그만큼 벗긴다. 늦게 끼운 것부터다.

    소지품이 준 뒤에 부른다(app/tables/items.py 의 remove_items). 착용하지 않은 것이 먼저 나간 셈이 된다.
    """
    extra = worn_of(sheet, entry_id)[held:]
    for row in extra:
        sheet.worn.remove(row)


def starting_wear(snapshot: Snapshot, pregen_index: int | None) -> list[ItemStackSnapshot]:
    """캐릭터 하나가 시작할 때 착용하는 줄들. 판의 시작 소지품 뒤에 고른 프리젠의 소지품이다. 착용을 적은 줄만."""
    stacks = list(snapshot.starting_items)
    if pregen_index is not None:
        stacks.extend(snapshot.pregens[pregen_index].items)
    return [stack for stack in stacks if stack.wear]


def dress(table_id: uuid.UUID, sheet: TableSheet, snapshot: Snapshot, pregen_index: int | None) -> None:
    """
    방금 받은 시트에 시작할 때의 착용을 끼운다. 시작 소지품을 준 바로 뒤에 부른다.

    판에 굳을 때 칸이 맞고 겹치지 않는지 봤다(Snapshot.require_fitting_wear). 그대로 끼운다.
    """
    for stack in starting_wear(snapshot, pregen_index):
        sheet.worn.append(TableWorn(table_id=table_id, entry_id=stack.entry_id, slots=list(stack.wear)))


def slot_order(ruleset: Ruleset) -> dict[str, int]:
    """규칙의 칸의 차례. 보여 줄 때 착용을 이 차례로 놓는다."""
    return {slot.key: index for index, slot in enumerate(ruleset.equipment_slots)}


def in_slot_order(rows: Sequence[TableWorn], ruleset: Ruleset) -> list[TableWorn]:
    """착용들을 규칙의 칸의 차례로 놓는다. 여러 칸을 차지한 것은 그중 앞의 칸의 자리다."""
    order = slot_order(ruleset)
    return sorted(rows, key=lambda row: min(order.get(slot, len(order)) for slot in row.slots))


def slot_names(ruleset: Ruleset, slots: Sequence[str]) -> list[str]:
    """칸의 이름표를 이름으로. 규칙에 없는 이름표는 그대로 둔다."""
    names = {slot.key: slot.name for slot in ruleset.equipment_slots}
    return [names.get(slot, slot) for slot in slots]
