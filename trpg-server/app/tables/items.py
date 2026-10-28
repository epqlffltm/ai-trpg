# trpg-server/app/tables/items.py

"""
캐릭터의 소지품을 다루는 규칙(#202). 무엇을 받고, 몇 개까지 갖고, 어떻게 늘고 주는가.

DB 를 모른다. 이미 읽어 온 시트와 판을 받아 소지품의 행(TableItem)을 고친다. 저장은 부르는 쪽이 한다.

  - 시작 소지품: 캐릭터가 시트를 받을 때 함께 받는다. 판의 시작 소지품에 프리젠의 소지품을 더한 것이다.
    처음 시작할 때도, 죽은 캐릭터의 뒤를 이을 새 캐릭터가 들어올 때도 같다. 앞 캐릭터의 것을 물려받지 않는다.
  - 한 가지를 99 개(ITEM_STACK_MAX)까지 갖는다. 넘게 주면 거절한다. 조용히 잘라 버리지 않는다.
  - 0 개가 되면 그 줄을 지운다.
"""

import uuid
from dataclasses import dataclass

from app.assets.models import ITEM_STACK_MAX, ItemKind, ItemRarity
from app.assets.scenarios.snapshot import ItemStackSnapshot, ItemThrowSnapshot, Snapshot, item_entries, item_rule_of
from app.engine import item_effects
from app.engine.item_aids import ItemAid
from app.engine.item_effects import Effect
from app.engine.ruleset import Resistance
from app.tables import equipment
from app.tables.errors import Conflict, TableConflictError, TableOptionError
from app.tables.models import TableItem, TableSheet


@dataclass(frozen=True)
class CatalogItem:
    """
    판에 있는 물건 하나. 이름은 로어북 항목의 이름, 종류와 효과와 등급과 값은 아이템 규칙의 것이다.

    effects 는 쓰면 대상에게 일어나는 일들이다(#800, app/engine/item_effects.py). 소모품에만 있다.

    price 는 상인이 파는 값이다(#278). 비어 있으면 사고팔 수 없다.
    slots 는 착용할 때 들어갈 수 있는 규칙의 칸, slot_count 는 차지하는 칸의 수다(#276). slots 가 비면 착용하지 않는다.
    attack 은 무기의 공격 보정, defense 는 차지한 칸의 방어, guard 는 모든 부위의 방어다(#276). 없으면 None.
    ap 는 무기의 관통력, ward 는 불굴 세이브의 값이다(#276). 없으면 None.
    lock 은 문에 다는 자물쇠 물건인가다(#281). 열쇠와 따는 판정은 판에 있다.
    throw 는 던지는 판정이다(#277). 던질 수 없는 물건이면 None.
    aids 는 이 물건이 거드는 행동들이다(#802, app/engine/item_aids.py). 행동에 붙여 쓰면 판정에 보정을 더한다.
    resistances 는 착용하고 있는 동안 생기는 저항이다(#886 ②, app/tables/resistances.py).
    nature 는 무기로 친 피해의 성질이다(#886 ③). 무기가 아니거나 성질이 없으면 None.
    """

    entry_id: uuid.UUID
    name: str
    kind: ItemKind
    effects: tuple[Effect, ...] = ()
    rarity: ItemRarity = ItemRarity.NORMAL
    price: int | None = None
    slots: tuple[str, ...] = ()
    slot_count: int = 1
    attack: int | None = None
    defense: int | None = None
    guard: int | None = None
    ap: int | None = None
    ward: int | None = None
    lock: bool = False
    throw: ItemThrowSnapshot | None = None
    aids: tuple[ItemAid, ...] = ()
    resistances: tuple[Resistance, ...] = ()
    nature: str | None = None


def catalog(snapshot: Snapshot) -> dict[uuid.UUID, CatalogItem]:
    """판의 물건 전부. 항목의 id 로 찾는다. 로어북의 순서, 그 안의 항목 순서다."""
    items = {}
    for entry in item_entries(snapshot):
        rule = item_rule_of(snapshot, entry.id)
        items[entry.id] = CatalogItem(
            entry_id=entry.id,
            name=entry.name,
            kind=rule.kind,
            effects=tuple(rule.effects),
            rarity=rule.rarity,
            price=rule.price,
            slots=tuple(rule.slots),
            slot_count=rule.slot_count,
            attack=rule.attack,
            defense=rule.defense,
            guard=rule.guard,
            ap=rule.ap,
            ward=rule.ward,
            lock=rule.lock is not None,
            throw=rule.throw,
            aids=tuple(rule.aids),
            resistances=tuple(rule.resistances),
            nature=rule.nature,
        )
    return items


def takes_target(item: CatalogItem) -> bool:
    """쓰면 누군가에게 드는 소모품인가. 효과가 있다(#800). 없으면 쓰고 없어질 뿐이다(연막탄)."""
    return bool(item.effects)


def is_harmful(item: CatalogItem) -> bool:
    """쓰면 대상을 해치는 소모품인가. 피해나 부상의 효과가 있다(#800). 동료에게는 아직 쓰지 못한다."""
    return item_effects.is_harmful(item.effects)


def require_in_catalog(items: dict[uuid.UUID, CatalogItem], entry_id: uuid.UUID) -> CatalogItem:
    """판의 물건인지 확인한다. 아니면 TableOptionError(entry_id). 인물이나 장소를 소지품으로 줄 수 없다."""
    item = items.get(entry_id)
    if item is None:
        raise TableOptionError('entry_id')
    return item


def starting_stacks(snapshot: Snapshot, pregen_index: int | None) -> list[ItemStackSnapshot]:
    """
    캐릭터 하나가 시작할 때 받는 소지품. 판의 시작 소지품 뒤에 고른 프리젠의 소지품을 붙인다.

    같은 물건이 둘 다에 있으면 개수를 합친다. 합쳐서 한 가지의 상한을 넘으면 상한까지다.
    제작자가 둘을 따로 적었다. 게시할 때 둘을 합친 것까지 막지는 않는다.
    """
    stacks = list(snapshot.starting_items)
    if pregen_index is not None:
        stacks.extend(snapshot.pregens[pregen_index].items)
    counts: dict[uuid.UUID, int] = {}
    for stack in stacks:
        counts[stack.entry_id] = min(counts.get(stack.entry_id, 0) + stack.count, ITEM_STACK_MAX)
    return [ItemStackSnapshot(entry_id=entry_id, count=count) for entry_id, count in counts.items()]


def give_starting_items(table_id: uuid.UUID, sheet: TableSheet, stacks: list[ItemStackSnapshot]) -> None:
    """방금 받은 시트에 시작 소지품을 준다. 시트에는 아직 소지품이 없다."""
    for stack in stacks:
        sheet.items.append(TableItem(table_id=table_id, entry_id=stack.entry_id, count=stack.count))


def equip(table_id: uuid.UUID, sheet: TableSheet, snapshot: Snapshot, pregen_index: int | None) -> None:
    """새 캐릭터의 시트에 그 캐릭터가 받을 시작 소지품을 준다. 시트를 준 바로 뒤에 부른다."""
    give_starting_items(table_id, sheet, starting_stacks(snapshot, pregen_index))


def in_catalog_order(rows: list[TableItem], items: dict[uuid.UUID, CatalogItem]) -> list[TableItem]:
    """
    가진 물건들을 판의 물건 순서로 놓는다. 보여 주고 서술자에게 줄 때 늘 같은 순서여야 한다.

    가진 순서(만든 시각)로 놓지 않는 까닭: 시작 소지품은 한 트랜잭션에서 함께 만들어 시각이 같다.
    """
    order = {entry_id: index for index, entry_id in enumerate(items)}
    return sorted(rows, key=lambda row: order[row.entry_id])


def find_item(sheet: TableSheet, entry_id: uuid.UUID) -> TableItem | None:
    """이 캐릭터가 가진 그 물건의 줄. 없으면 None."""
    return next((item for item in sheet.items if item.entry_id == entry_id), None)


def count_of(sheet: TableSheet, entry_id: uuid.UUID) -> int:
    """이 캐릭터가 가진 그 물건의 개수. 없으면 0 이다."""
    item = find_item(sheet, entry_id)
    return item.count if item else 0


def add_items(table_id: uuid.UUID, sheet: TableSheet, entry_id: uuid.UUID, count: int) -> int:
    """
    이 캐릭터에게 그 물건을 count 개 더 준다. 준 뒤의 개수를 돌려준다.

    한 가지의 상한을 넘으면 TableConflictError(too_many_items). 아무것도 바꾸지 않는다.
    """
    total = count_of(sheet, entry_id) + count
    if total > ITEM_STACK_MAX:
        raise TableConflictError(Conflict.TOO_MANY_ITEMS)
    item = find_item(sheet, entry_id)
    if item is None:
        sheet.items.append(TableItem(table_id=table_id, entry_id=entry_id, count=count))
    else:
        item.count = total
    return total


def add_up_to(table_id: uuid.UUID, sheet: TableSheet, entry_id: uuid.UUID, count: int) -> int:
    """
    이 캐릭터에게 그 물건을 count 개까지 준다. 한 가지의 상한에 닿으면 거기까지만 준다. 준 개수를 돌려준다.

    퀘스트의 보상처럼 여럿에게 한꺼번에 주는 것에 쓴다. 한 사람이 가득 찼다고 모두의 보상을 막지 않는다.
    한 사람이 받는 것(건네기, 사기의 add_items)은 넘으면 거절한다. 받을 때 미리 보고 알린다.
    """
    given = min(count, ITEM_STACK_MAX - count_of(sheet, entry_id))
    add_items(table_id, sheet, entry_id, given)
    return given


def remove_items(sheet: TableSheet, entry_id: uuid.UUID, count: int) -> int:
    """
    이 캐릭터에게서 그 물건을 count 개 뺀다. 뺀 뒤의 개수를 돌려준다. 0 이 되면 그 줄을 지운다.
    착용하지 않은 것부터 나간다. 가진 것보다 착용한 것이 많아지면 그만큼 벗는다(app/tables/equipment.py, #276).

    가진 것보다 많이 빼려 하면 TableConflictError(not_enough_items). 아무것도 바꾸지 않는다.
    """
    item = find_item(sheet, entry_id)
    if item is None or item.count < count:
        raise TableConflictError(Conflict.NOT_ENOUGH_ITEMS)
    item.count -= count
    if item.count == 0:
        sheet.items.remove(item)
    equipment.trim(sheet, entry_id, item.count)
    return item.count
