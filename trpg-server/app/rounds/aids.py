# trpg-server/app/rounds/aids.py

"""
행동에 붙여 쓴 물건(#802, 거들기). 치료, 따기, 고치기, 부수기, 넘기가 함께 쓴다.

플레이어가 행동의 item 에 적은 물건 하나를 차례가 왔을 때 꺼낸다(take_aid). 받을 때 그 행동을 거드는 물건이고
가지고 있는지 봤다(require_aid). 그사이 건넸거나 내려놓았으면 맨손이다(not_held).
  - 굴리면 그 물건의 보정(bonus)을 판정에 더한다. 굴린 뒤 그 물건의 방식(wear)대로 하나 없어진다
    (늘, 실패하면 부러져, 안 없어짐. app/engine/item_aids.py 의 is_lost).
  - 굴리지 않았으면(문이 이미 열렸다, 도구가 없었다) 물건은 그대로다.
결과에는 쓴 물건, 더한 보정, 썼는가, 없어졌는가, 부러졌는가, 남은 개수를 적는다(aid_document).

DB 를 모른다. 시트의 소지품만 고친다. 저장하지 않는다.
"""

import uuid
from dataclasses import dataclass

from app.assets.scenarios.snapshot import read_snapshot
from app.engine.item_aids import AidAct, AidWear, ItemAid, aid_for, is_lost
from app.rounds.effects import Judging
from app.rounds.errors import ActionNotInRulesError, Conflict, RoundConflictError
from app.tables import items
from app.tables.items import CatalogItem
from app.tables.models import GameTable, TableMember

# 붙여 쓰려던 물건을 쓰지 못한 까닭. 차례가 왔을 때 더 가지고 있지 않았다
NOT_HELD = 'not_held'


def require_aid(table: GameTable, member: TableMember, entry_id: uuid.UUID, act: AidAct) -> None:
    """
    행동에 붙인 물건을 받을 때 본다. 판의 물건이 아니거나 그 행동을 거들지 않으면 ActionNotInRulesError(item),
    하나도 가지고 있지 않으면 RoundConflictError(item_not_held).
    """
    item = items.catalog(read_snapshot(table.content)).get(entry_id)
    if item is None or aid_for(item.aids, act) is None:
        raise ActionNotInRulesError('item')
    if member.sheet is None or items.count_of(member.sheet, entry_id) < 1:
        raise RoundConflictError(Conflict.ITEM_NOT_HELD)


def require_tool(needs_tool: bool, entry_id: uuid.UUID | None) -> None:
    """도구가 있어야 하는 판정인데 물건을 붙이지 않았으면 ActionNotInRulesError(item)."""
    if needs_tool and entry_id is None:
        raise ActionNotInRulesError('item')


@dataclass(frozen=True)
class TakenAid:
    """차례가 왔을 때 꺼낸 물건. 그 행동의 거들기(aid)와, 아직 가지고 있었는가(held)."""

    item: CatalogItem
    aid: ItemAid
    held: bool


@dataclass(frozen=True)
class AidUse:
    """붙여 쓴 물건을 어떻게 했나. 굴렸는가(rolled)와 굴린 뒤 하나 없어졌는가(lost)."""

    rolled: bool
    lost: bool


def take_aid(judging: Judging, member: TableMember, entry_id: uuid.UUID | None, act: AidAct) -> TakenAid | None:
    """행동에 붙인 물건을 꺼낸다. 적지 않았으면 None. 받을 때 그 행동을 거드는 판의 물건인지 봤다."""
    if entry_id is None:
        return None
    item = judging.items[entry_id]
    return TakenAid(item=item, aid=aid_for(item.aids, act), held=items.count_of(member.sheet, entry_id) >= 1)


def has_tool(taken: TakenAid | None) -> bool:
    """도구로 쓸 물건을 지금 가지고 있는가. 도구가 있어야 하는 문은 이것이 참이어야 굴린다."""
    return taken is not None and taken.held


def aid_bonus(taken: TakenAid | None) -> int:
    """판정에 더할 보정. 붙인 물건을 가지고 있으면 그 거들기의 보정, 아니면 0."""
    return taken.aid.bonus if has_tool(taken) else 0


def wear_aid(member: TableMember, taken: TakenAid | None, success: bool) -> AidUse:
    """
    굴린 뒤 붙여 쓴 물건을 그 방식대로 한다. 없어지면 소지품에서 하나 뺀다.

    가지고 있지 않았으면 아무 일도 없다.
    """
    if not has_tool(taken):
        return AidUse(rolled=True, lost=False)
    lost = is_lost(taken.aid.wear, success)
    if lost:
        items.remove_items(member.sheet, taken.item.entry_id, 1)
    return AidUse(rolled=True, lost=lost)


def aid_document(member: TableMember, taken: TakenAid | None, use: AidUse | None) -> dict | None:
    """
    붙여 쓴 물건을 결과에 적을 모양. 물건을 적지 않았으면 None.

    use 가 None 이면 굴리지 않았다(물건은 그대로다). used 는 판정에 보정을 더했는가, lost 는 하나 없어졌는가,
    broken 은 실패해서 부러졌는가(실패하면 부러지는 물건)다.
    """
    if taken is None:
        return None
    used = taken.held and use is not None
    lost = use is not None and use.lost
    return {
        'entry_id': str(taken.item.entry_id),
        'name': taken.item.name,
        'act': taken.aid.act,
        'bonus': taken.aid.bonus if used else 0,
        'used': used,
        'lost': lost,
        'broken': lost and taken.aid.wear == AidWear.ON_FAIL,
        'reason': None if taken.held else NOT_HELD,
        'remaining': items.count_of(member.sheet, taken.item.entry_id),
    }
