# game-server/app/tables/place_items.py

"""
테이블의 장소에 놓인 물건을 다루는 규칙(#279). 무엇이 어디에 몇 개 남았는가, 누가 보는가.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 남은 개수(TablePlaceItem)를 고친다. 저장은 부르는 쪽이 한다.

  - 시작할 때 판의 놓인 물건 줄마다 남은 개수를 하나씩 만든다. 판의 줄 순서가 번호(slot)다.
  - 보이는 물건은 그 장소에 서 본 뒤부터 보인다(테이블의 모두가 함께 안다). 서 본 적 없는 장소의 물건은 모른다.
    줍기(take)로 가져간다(app/rounds/place_item_actions.py).
  - 숨긴 물건은 아무에게도(방장에게도) 보이지 않는다. 찾기(search)의 판정으로 찾으면 찾은 사람이 갖고,
    상한을 넘어 남은 것은 그 자리에 보이는 물건으로 남는다.
  - 같은 장소의 같은 물건이 여러 줄이면(보이는 줄과 찾은 숨긴 줄) 합쳐 보인다. 가져갈 때는 줄 순서로 줄인다.
  - 0 이 된 줄은 지우지 않는다. 보이지 않을 뿐이다.
  - 캐릭터가 내려놓은 물건(put_down)도 같은 표에 보이는 줄로 둔다.
    그 장소의 같은 물건의 보이는 줄이 있으면 거기에 더하고, 없으면 판의 줄 뒤에 새 번호로 더한다.
    새 줄은 판에 없으므로 숨기지 않는다(찾는 판정이 없다).
"""

import uuid
from dataclasses import dataclass

from app.assets.models import PlaceItemVisibility
from app.assets.scenarios.snapshot import PlaceItemSnapshot, Snapshot
from app.tables.models import GameTable, TablePlaceItem


@dataclass(frozen=True)
class Pile:
    """한 장소에 보이는 물건 한 가지. 줄이 여럿이면 합친 개수다."""

    entry_id: uuid.UUID
    count: int


def make_place_item(table_id: uuid.UUID, slot: int, rule: PlaceItemSnapshot) -> TablePlaceItem:
    """판의 놓인 물건 한 줄의 남은 개수. 처음에는 판에 적힌 개수 그대로다."""
    return TablePlaceItem(
        table_id=table_id,
        slot=slot,
        place_id=rule.place_id,
        entry_id=rule.entry_id,
        count=rule.count,
        hidden=rule.visibility == PlaceItemVisibility.HIDDEN,
    )


def make_place_items(table_id: uuid.UUID, snapshot: Snapshot) -> list[TablePlaceItem]:
    """시작할 때 판의 놓인 물건 줄마다 남은 개수를 하나씩 만든다. 놓인 물건이 없는 판이면 빈 목록이다."""
    return [make_place_item(table_id, slot, rule) for slot, rule in enumerate(snapshot.place_items)]


def visible_rows(table: GameTable, place_id: uuid.UUID, entry_id: uuid.UUID | None = None) -> list[TablePlaceItem]:
    """그 장소에 보이게 남은 줄들. 줄 순서다. entry_id 를 주면 그 물건의 줄만이다."""
    return [
        row
        for row in table.place_items
        if row.place_id == place_id
        and not row.hidden
        and row.count > 0
        and (entry_id is None or row.entry_id == entry_id)
    ]


def hidden_rows(table: GameTable, place_id: uuid.UUID) -> list[TablePlaceItem]:
    """그 장소에 아직 찾지 않은 숨긴 줄들. 줄 순서다."""
    return [row for row in table.place_items if row.place_id == place_id and row.hidden and row.count > 0]


def piles_at(table: GameTable, place_id: uuid.UUID) -> list[Pile]:
    """그 장소에 보이는 물건들. 같은 물건은 합친다. 처음 나온 줄의 순서다."""
    counts: dict[uuid.UUID, int] = {}
    for row in visible_rows(table, place_id):
        counts[row.entry_id] = counts.get(row.entry_id, 0) + row.count
    return [Pile(entry_id, count) for entry_id, count in counts.items()]


def available(table: GameTable, place_id: uuid.UUID, entry_id: uuid.UUID) -> int:
    """그 장소에 보이게 남은 그 물건의 개수."""
    return sum(row.count for row in visible_rows(table, place_id, entry_id))


def take_from(table: GameTable, place_id: uuid.UUID, entry_id: uuid.UUID, count: int) -> None:
    """그 장소의 보이는 그 물건을 count 개 줄인다. 줄 순서로 줄인다. 남은 것보다 많이 부르지 않는다."""
    left = count
    for row in visible_rows(table, place_id, entry_id):
        used = min(row.count, left)
        row.count -= used
        left -= used
        if left == 0:
            return


def visible_row(table: GameTable, place_id: uuid.UUID, entry_id: uuid.UUID) -> TablePlaceItem | None:
    """그 장소의 그 물건의 보이는 줄 하나. 다 가져가 0 이 된 줄도 된다. 없으면 None. 줄 순서로 처음 것이다."""
    return next(
        (row for row in table.place_items if row.place_id == place_id and row.entry_id == entry_id and not row.hidden),
        None,
    )


def next_slot(table: GameTable) -> int:
    """새 줄의 번호. 판의 줄과 앞서 더한 줄의 뒤다."""
    return max((row.slot for row in table.place_items), default=-1) + 1


def put_down(table: GameTable, place_id: uuid.UUID, entry_id: uuid.UUID, count: int) -> None:
    """그 장소에 그 물건을 count 개 보이게 둔다. 같은 물건의 보이는 줄이 있으면 더하고, 없으면 새 줄을 만든다."""
    row = visible_row(table, place_id, entry_id)
    if row is not None:
        row.count += count
        return
    table.place_items.append(
        TablePlaceItem(
            table_id=table.id, slot=next_slot(table), place_id=place_id, entry_id=entry_id, count=count, hidden=False
        )
    )


def uncover(row: TablePlaceItem, kept: int) -> int:
    """
    찾은 숨긴 줄에서 kept 개를 가져가고 나머지를 보이는 줄로 남긴다. 그 자리에 남은 개수를 돌려준다.

    kept 는 찾은 사람이 상한까지 받은 개수다(app/tables/items.py 의 add_up_to).
    """
    row.hidden = False
    row.count -= kept
    return row.count


def seen_places(table: GameTable) -> frozenset[uuid.UUID]:
    """테이블의 누군가가 서 본 장소들. 그곳의 보이는 물건만 보인다."""
    return frozenset(visit.entry_id for visit in table.visits)
