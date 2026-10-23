# trpg-server/app/rounds/trades.py

"""
돈이 오가는 행동(#278). 상인에게서 사기(buy), 상인에게 팔기(sell), 앉은 다른 사람에게 돈 건네기(pay).
선언을 받을 때 보고(accept_buy, accept_sell, accept_pay), 라운드가 닫힐 때 차례가 오면 정한다(judge_*).

돈과 값은 판이 정하고 엔진이 옮긴다. 서술(AI)은 돈을 주거나 빼앗지 못한다. 방장도 PC 라서 돈을 정하지 않는다.
  - 화폐가 없는 판에서는 셋 다 할 수 없다(ActionNotInRulesError kind).
  - 상인: 이번 장면의 인물 중 판의 NPC 시트에 상인(merchant)으로 적힌 사람이다. 살아 있고 적대하지 않아야 거래한다.
    상인의 소지품(inventory) 중 값이 있는 물건을 판다. 소지품의 개수가 재고다. 장비는 팔지 않는다.
    값이 있는 물건이면 무엇이든 사 준다. 사 준 물건은 상인의 재고가 되지 않는다(판에 적은 줄만 센다).
    상인이 가진 돈은 세지 않는다. 늘 살 돈이 있다.
  - 값: 살 때는 물건 하나의 값 × 개수, 팔 때는 하나의 값에 화폐의 백분율을 곱해 내림한 것 × 개수다
    (app/tables/money.py). 백분율이 0 인 판의 상인은 사 주지 않는다.
  - 다 하거나 하나도 하지 않는다. 받을 때 보고, 차례가 오면 다시 본다. 그사이 앞사람이 재고를 사 갔거나,
    돈을 건넸거나, 상인을 쳐서 쓰러뜨렸을 수 있다. 그때는 아무것도 바뀌지 않고 까닭(reason)을 적는다.

DB 를 모른다. 시트의 돈과 소지품, 상인이 지닌 것을 고친다. 저장하지 않는다.
"""

import uuid

from app.assets.models import ITEM_STACK_MAX, NpcAttitude
from app.assets.scenarios.snapshot import CurrencySnapshot, Snapshot, read_snapshot
from app.engine.action import BuyAction, PayAction, SellAction
from app.rounds import item_actions
from app.rounds.cast import CastMember, Scene, find_cast_member, find_reachable
from app.rounds.effects import Judging
from app.rounds.errors import ActionNotInRulesError, ActionTargetError, Conflict, RoundConflictError
from app.tables import carried, items, money, npc_items, sheets
from app.tables import state as table_state
from app.tables.carried import Carried
from app.tables.items import CatalogItem
from app.tables.models import GameTable, NpcStatus, TableMember

# 결과의 side. 사기와 팔기가 같은 모양(trade)이라 어느 쪽인지 적는다
BUY = 'buy'
SELL = 'sell'


class Reason:
    """사거나 팔거나 건네지 못한 까닭. 결과의 reason 에 적는다."""

    # 차례가 왔을 때 상인이 쓰러졌거나 죽었거나 적대했다
    UNAVAILABLE = 'unavailable'
    # 차례가 왔을 때 상인의 재고가 모자랐다(앞사람이 사 갔다)
    OUT_OF_STOCK = 'out_of_stock'
    # 차례가 왔을 때 돈이 모자랐다
    NOT_ENOUGH_MONEY = 'not_enough_money'
    # 차례가 왔을 때 그 물건을 그만큼 가지고 있지 않았다
    NOT_HELD = 'not_held'
    # 산 물건을 더 가질 수 없었다(한 가지 99 개)
    FULL = 'full'
    # 받을 돈을 더 가질 수 없었다(돈의 상한)
    TOO_MUCH_MONEY = 'too_much_money'
    # 돈을 받을 사람이 떠났거나 죽었다
    TARGET_GONE = 'target_gone'


# --- 상인 ---


def is_merchant(merchant: CastMember) -> bool:
    """판의 NPC 시트에 상인으로 적힌 인물인가. 시트가 없는 인물은 상인이 아니다."""
    return merchant.definition is not None and merchant.definition.merchant


def is_open(merchant: CastMember) -> bool:
    """지금 거래하는가. 살아 있고(쓰러지지 않았고) 적대하지 않는다."""
    return merchant.npc.status == NpcStatus.ALIVE and merchant.npc.attitude != NpcAttitude.HOSTILE


def stock_of(merchant: CastMember, entry_id: uuid.UUID) -> Carried | None:
    """상인이 파는 그 물건의 줄. 소지품(장비가 아닌 것)에 지금 있어야 한다. 없으면 None."""
    held = [line for line in npc_items.carried(merchant.npc, merchant.definition) if not line.equipped]
    return carried.find_carried(held, entry_id)


def unit_count(line: Carried | None) -> int:
    """재고의 개수. 줄이 없으면 0 이다."""
    return line.count if line is not None else 0


# --- 받을 때 ---


def require_currency(snapshot: Snapshot) -> CurrencySnapshot:
    """판의 화폐. 돈이 없는 판이면 ActionNotInRulesError(kind)."""
    if snapshot.currency is None:
        raise ActionNotInRulesError('kind')
    return snapshot.currency


def require_priced(snapshot: Snapshot, entry_id: uuid.UUID) -> CatalogItem:
    """사고팔 수 있는 판의 물건인지 본다. 판에 없거나 값이 없으면 ActionNotInRulesError(item)."""
    item = items.catalog(snapshot).get(entry_id)
    if item is None or item.price is None:
        raise ActionNotInRulesError('item')
    return item


def require_merchant(scene: Scene, member: TableMember, npc_id: uuid.UUID) -> CastMember:
    """
    거래할 상인. 이번 장면의 인물이 아니거나 거래하는 캐릭터와 다른 장소에 있으면 ActionTargetError(npc, #282),
    상인이 아니면 RoundConflictError(not_merchant),
    쓰러졌거나 죽었거나 적대하면 RoundConflictError(merchant_unavailable).
    """
    found = find_reachable(scene.cast, member, npc_id)
    if found is None:
        raise ActionTargetError('npc')
    if not is_merchant(found):
        raise RoundConflictError(Conflict.NOT_MERCHANT)
    if not is_open(found):
        raise RoundConflictError(Conflict.MERCHANT_UNAVAILABLE)
    return found


def require_money(member: TableMember, amount: int) -> None:
    """그만큼의 돈을 가지고 있는지 본다. 아니면 RoundConflictError(not_enough_money)."""
    if member.sheet is None or member.sheet.money < amount:
        raise RoundConflictError(Conflict.NOT_ENOUGH_MONEY)


def require_room(member: TableMember, amount: int) -> None:
    """그만큼의 돈을 더 가질 수 있는지 본다. 아니면 RoundConflictError(too_much_money)."""
    if money.room_for(member.sheet) < amount:
        raise RoundConflictError(Conflict.TOO_MUCH_MONEY)


def accept_buy(table: GameTable, member: TableMember, scene: Scene, action: BuyAction) -> dict:
    """
    사는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 화폐가 없는 판이면 ActionNotInRulesError(kind). 값이 없는 물건이면 ActionNotInRulesError(item).
      - 상인이 맞지 않으면 require_merchant 와 같다.
      - 상인의 재고가 모자라면 RoundConflictError(out_of_stock).
      - 돈이 모자라면 RoundConflictError(not_enough_money).
      - 그 물건을 더 가질 수 없으면 RoundConflictError(recipient_full).
    """
    snapshot = read_snapshot(table.content)
    require_currency(snapshot)
    item = require_priced(snapshot, action.item)
    merchant = require_merchant(scene, member, action.npc)
    if unit_count(stock_of(merchant, action.item)) < action.count:
        raise RoundConflictError(Conflict.OUT_OF_STOCK)
    require_money(member, money.buying_price(item.price, action.count))
    if items.count_of(member.sheet, action.item) + action.count > ITEM_STACK_MAX:
        raise RoundConflictError(Conflict.RECIPIENT_FULL)
    return action.model_dump(mode='json')


def accept_sell(table: GameTable, member: TableMember, scene: Scene, action: SellAction) -> dict:
    """
    파는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 화폐가 없거나 상인이 사 주지 않는 판(백분율 0)이면 ActionNotInRulesError(kind).
      - 값이 없는 물건이면 ActionNotInRulesError(item).
      - 상인이 맞지 않으면 require_merchant 와 같다.
      - 그만큼 가지고 있지 않으면 RoundConflictError(item_not_held).
      - 받을 돈을 더 가질 수 없으면 RoundConflictError(too_much_money).
    """
    snapshot = read_snapshot(table.content)
    currency = require_currency(snapshot)
    if currency.sell_percent == 0:
        raise ActionNotInRulesError('kind')
    item = require_priced(snapshot, action.item)
    require_merchant(scene, member, action.npc)
    if member.sheet is None or items.count_of(member.sheet, action.item) < action.count:
        raise RoundConflictError(Conflict.ITEM_NOT_HELD)
    require_room(member, money.selling_price(currency, item.price, action.count))
    return action.model_dump(mode='json')


def accept_pay(table: GameTable, member: TableMember, action: PayAction) -> dict:
    """
    돈을 건네는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 화폐가 없는 판이면 ActionNotInRulesError(kind).
      - 받는 사람이 자기 자신이거나 앉은 사람이 아니면 ActionTargetError(target), 죽었으면 RoundConflictError.
      - 돈이 모자라면 RoundConflictError(not_enough_money).
      - 받는 쪽이 더 가질 수 없으면 RoundConflictError(too_much_money).
    """
    require_currency(read_snapshot(table.content))
    if action.target == member.user_id:
        raise ActionTargetError('target')
    recipient = table_state.find_member(table, action.target)
    if recipient is None or recipient.sheet is None:
        raise ActionTargetError('target')
    if sheets.is_dead(recipient):
        raise RoundConflictError(Conflict.RECIPIENT_DEAD)
    require_money(member, action.amount)
    require_room(recipient, action.amount)
    return action.model_dump(mode='json')


# --- 차례가 왔을 때 ---


def describe_trade(member: TableMember, merchant: CastMember, item: CatalogItem, side: str, count: int) -> dict:
    """사기와 팔기의 결과에서 언제나 같은 칸들. 누가, 어느 상인과, 무엇을, 몇 개, 어느 쪽으로."""
    return {
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'side': side,
        'npc_id': str(merchant.entry_id),
        'npc_name': merchant.name,
        'entry_id': str(item.entry_id),
        'name': item.name,
        'count': count,
    }


def buy_shortfall(member: TableMember, merchant: CastMember, action: BuyAction, cost: int) -> str | None:
    """차례가 왔을 때 사지 못하는 까닭. 살 수 있으면 None. 상인, 재고, 돈, 상한의 차례로 본다."""
    if not is_open(merchant):
        return Reason.UNAVAILABLE
    if unit_count(stock_of(merchant, action.item)) < action.count:
        return Reason.OUT_OF_STOCK
    if member.sheet.money < cost:
        return Reason.NOT_ENOUGH_MONEY
    if items.count_of(member.sheet, action.item) + action.count > ITEM_STACK_MAX:
        return Reason.FULL
    return None


def hand_over_stock(judging: Judging, member: TableMember, merchant: CastMember, action: BuyAction, cost: int) -> None:
    """돈을 내고 상인의 재고에서 산 사람에게 물건을 옮긴다. buy_shortfall 이 None 일 때만 부른다."""
    line = stock_of(merchant, action.item)
    npc_items.set_count(merchant.npc, line.slot, line.count - action.count)
    items.add_items(judging.table.id, member.sheet, action.item, action.count)
    money.remove_money(member.sheet, cost)


def judge_buy(judging: Judging, member: TableMember, action: BuyAction) -> dict:
    """
    차례가 온 사람이 상인에게서 산다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    price 는 낸(내려던) 돈, traded 가 참이면 샀다. total 은 그 물건을 가진 개수, money 는 가진 돈이다.
    장면의 인물은 라운드 동안 바뀌지 않으므로, 받을 때 장면에 있던 상인은 차례가 올 때도 있다.
    """
    merchant = find_cast_member(judging.cast, action.npc)
    item = judging.items[action.item]
    cost = money.buying_price(item.price, action.count)
    reason = buy_shortfall(member, merchant, action, cost)
    if reason is None:
        hand_over_stock(judging, member, merchant, action, cost)
    return {'trade': trade_result(member, merchant, item, BUY, action.count, cost, reason)}


def judge_sell(judging: Judging, member: TableMember, action: SellAction) -> dict:
    """
    차례가 온 사람이 상인에게 판다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    price 는 받은(받으려던) 돈이다. 판 물건은 사라진다. 상인의 재고가 되지 않는다.
    """
    merchant = find_cast_member(judging.cast, action.npc)
    item = judging.items[action.item]
    gain = money.selling_price(judging.snapshot.currency, item.price, action.count)
    reason = sell_shortfall(member, merchant, action, gain)
    if reason is None:
        items.remove_items(member.sheet, action.item, action.count)
        money.add_money(member.sheet, gain)
    return {'trade': trade_result(member, merchant, item, SELL, action.count, gain, reason)}


def sell_shortfall(member: TableMember, merchant: CastMember, action: SellAction, gain: int) -> str | None:
    """차례가 왔을 때 팔지 못하는 까닭. 팔 수 있으면 None. 상인, 가진 것, 돈의 상한의 차례로 본다."""
    if not is_open(merchant):
        return Reason.UNAVAILABLE
    if items.count_of(member.sheet, action.item) < action.count:
        return Reason.NOT_HELD
    if money.room_for(member.sheet) < gain:
        return Reason.TOO_MUCH_MONEY
    return None


def trade_result(
    member: TableMember, merchant: CastMember, item: CatalogItem, side: str, count: int, price: int, reason: str | None
) -> dict:
    """사기와 팔기의 결과 문서. 했는지(traded), 오간 돈(price), 그 뒤에 가진 개수(total)와 돈(money)."""
    return {
        **describe_trade(member, merchant, item, side, count),
        'price': price,
        'traded': reason is None,
        'reason': reason,
        'total': items.count_of(member.sheet, item.entry_id),
        'money': member.sheet.money,
    }


def judge_pay(judging: Judging, member: TableMember, action: PayAction) -> dict:
    """
    차례가 온 사람이 돈을 건넨다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    remaining 은 건넨 뒤에 가진 돈, target_total 은 받은 사람이 가진 돈이다(받을 사람이 없으면 None).
    """
    recipient = item_actions.living(table_state.find_member(judging.table, action.target))
    reason = pay_shortfall(member, recipient, action)
    if reason is None:
        money.remove_money(member.sheet, action.amount)
        money.add_money(recipient.sheet, action.amount)
    paid = {
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'amount': action.amount,
        'paid': reason is None,
        'reason': reason,
        'target': item_actions.person(recipient) or {'user_id': str(action.target), 'character_name': None},
        'remaining': member.sheet.money,
        'target_total': recipient.sheet.money if recipient is not None else None,
    }
    return {'pay': paid}


def pay_shortfall(member: TableMember, recipient: TableMember | None, action: PayAction) -> str | None:
    """차례가 왔을 때 돈을 건네지 못하는 까닭. 건넬 수 있으면 None. 돈, 받는 사람, 그 사람의 상한의 차례로 본다."""
    if member.sheet.money < action.amount:
        return Reason.NOT_ENOUGH_MONEY
    if recipient is None:
        return Reason.TARGET_GONE
    if money.room_for(recipient.sheet) < action.amount:
        return Reason.TOO_MUCH_MONEY
    return None
