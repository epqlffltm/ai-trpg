# trpg-server/app/tables/resistances.py

"""
저항(#886 ②). 캐릭터, NPC, 몬스터가 지금 어느 성질을 막는가.

저항 한 줄은 성질과 단계(저항, 면역, 약점)다(app/engine/ruleset.py 의 Resistance). 저항이 오는 곳은 셋이다.
  - 시트: 캐릭터의 시트(테이블의 시트에 복사해 둔다)와 NPC 시트의 타고난 저항
  - 착용한 장비: 아이템 규칙의 저항. 착용하고 있는 동안만이다. 소지품으로 들고만 있으면 들지 않는다
  - 부상(상태): 부상의 정의의 저항. 입고 있는 동안만이다(돌 피부)
몬스터는 여기에 예전부터의 면역(타입마다의 면역과 시트의 immune, vulnerable, app/tables/monsters.py)을 더한다.

막는 것은 저항과 면역이다. 한 곳이라도 막으면 막는다. 약점은 부상과 수치를 내리는 맞추기에 아무것도 하지 않는다
(피해를 더 받는 것은 #886 ③ 이다). 막는 성질의 부상은 입지 않고(app/rounds/injuries.py 의 wound),
그 성질의 수치를 내리는 맞추기도 받지 않는다(app/engine/item_effects.py 의 is_resisted).

DB 를 모른다. 이미 읽어 온 시트와 상태와 판을 받아 읽기만 한다. 고치지 않는다.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from app.assets.scenarios.snapshot import MonsterSnapshot, NpcSheetSnapshot, Snapshot, monster_of, own_npc_sheet
from app.engine import injury as injury_rules
from app.engine.ruleset import Resistance, Ruleset, blocked_natures
from app.tables import injuries, monster_items, monsters, npc_items
from app.tables import items as table_items
from app.tables.carried import Carried
from app.tables.items import CatalogItem
from app.tables.models import TableInjury, TableMonster, TableNpc, TableSheet


def of_sheet(sheet: TableSheet) -> list[Resistance]:
    """테이블의 시트에 복사해 둔 타고난 저항. 칸이 생기기 전의 시트는 비어 있다."""
    return [Resistance.model_validate(one) for one in sheet.resistances or []]


def worn_by(items: dict[uuid.UUID, CatalogItem], entry_ids: Iterable[uuid.UUID]) -> list[Resistance]:
    """착용한 물건들의 저항. 판에 없는 물건(있을 수 없다)은 건너뛴다."""
    return [one for entry_id in entry_ids if entry_id in items for one in items[entry_id].resistances]


def wearing(held: list[Carried]) -> list[uuid.UUID]:
    """NPC 나 몬스터가 지닌 줄 중 착용한 장비의 물건들."""
    return [line.entry_id for line in held if line.equipped and line.wear]


def granted_by(ruleset: Ruleset, rows: list[TableInjury]) -> list[Resistance]:
    """입고 있는 부상들이 주는 저항. 규칙에 없는 부상(규칙이 바뀐 판)은 아무것도 주지 않는다."""
    granted = []
    for row in injuries.active(rows):
        definition = injury_rules.find_injury(ruleset, row.injury)
        if definition is not None:
            granted.extend(definition.resistances)
    return granted


def of_member(ruleset: Ruleset, items: dict[uuid.UUID, CatalogItem], sheet: TableSheet) -> list[Resistance]:
    """캐릭터 하나의 지금 저항. 시트, 착용한 물건, 입은 부상의 차례다."""
    worn = worn_by(items, [row.entry_id for row in sheet.worn])
    return [*of_sheet(sheet), *worn, *granted_by(ruleset, sheet.injuries)]


def of_npc(
    ruleset: Ruleset, items: dict[uuid.UUID, CatalogItem], npc: TableNpc, definition: NpcSheetSnapshot | None
) -> list[Resistance]:
    """NPC 하나의 지금 저항. NPC 시트, 착용한 장비, 입은 부상의 차례다. 시트를 적지 않은 인물은 부상의 것뿐이다."""
    own = list(definition.resistances) if definition is not None else []
    worn = worn_by(items, wearing(npc_items.carried(npc, definition)))
    return [*own, *worn, *granted_by(ruleset, npc.injuries)]


def of_monster(
    ruleset: Ruleset, items: dict[uuid.UUID, CatalogItem], monster: TableMonster, definition: MonsterSnapshot
) -> list[Resistance]:
    """몬스터 한 마리의 착용한 장비와 입은 부상의 저항. 타입과 시트의 면역은 따로다(monster_blocked)."""
    worn = worn_by(items, wearing(monster_items.carried(monster, definition)))
    return [*worn, *granted_by(ruleset, monster.injuries)]


def member_blocked(ruleset: Ruleset, items: dict[uuid.UUID, CatalogItem], sheet: TableSheet) -> frozenset[str]:
    """캐릭터 하나가 지금 막는 성질들."""
    return blocked_natures(of_member(ruleset, items, sheet))


def npc_blocked(
    ruleset: Ruleset, items: dict[uuid.UUID, CatalogItem], npc: TableNpc, definition: NpcSheetSnapshot | None
) -> frozenset[str]:
    """NPC 하나가 지금 막는 성질들."""
    return blocked_natures(of_npc(ruleset, items, npc, definition))


def monster_blocked(
    ruleset: Ruleset, items: dict[uuid.UUID, CatalogItem], monster: TableMonster, definition: MonsterSnapshot
) -> frozenset[str]:
    """몬스터 한 마리가 지금 막는 성질들. 타입과 시트의 면역(#799)에 착용한 장비와 입은 부상의 저항을 더한다."""
    return monsters.immunities(ruleset, definition) | blocked_natures(of_monster(ruleset, items, monster, definition))


@dataclass(frozen=True)
class Guard:
    """
    판 하나에서 누가 지금 어느 성질을 막는지 묻는 곳. 판의 규칙과 물건과 판(인물과 몬스터의 정의)이다.

    라운드를 닫을 때 부상을 끝내거나(후유증) 수치의 문턱을 맞출 때 쓴다. 판정의 중간에는 이미 모아 둔 것을 쓴다
    (app/rounds/resisting.py).
    """

    ruleset: Ruleset
    items: dict[uuid.UUID, CatalogItem]
    snapshot: Snapshot

    def member(self, sheet: TableSheet) -> frozenset[str]:
        """캐릭터 하나가 막는 성질들."""
        return member_blocked(self.ruleset, self.items, sheet)

    def npc(self, npc: TableNpc) -> frozenset[str]:
        """NPC 하나가 막는 성질들."""
        return npc_blocked(self.ruleset, self.items, npc, own_npc_sheet(self.snapshot, npc.entry_id))

    def monster(self, monster: TableMonster) -> frozenset[str]:
        """몬스터 한 마리가 막는 성질들."""
        return monster_blocked(self.ruleset, self.items, monster, monster_of(self.snapshot, monster.monster_id))


def guard_of(snapshot: Snapshot) -> Guard:
    """판 하나의 Guard. 물건을 모은다(app/tables/items.py 의 catalog)."""
    return Guard(snapshot.rulebook.rules, table_items.catalog(snapshot), snapshot)
