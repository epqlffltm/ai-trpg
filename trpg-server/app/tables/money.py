# trpg-server/app/tables/money.py

"""
캐릭터의 돈을 다루는 규칙(#278). 얼마를 받고, 얼마까지 갖고, 어떻게 늘고 주는가.

돈은 판의 화폐(Snapshot.currency)로 센다. 결제의 크레딧과 상관없다. 게임 안의 숫자이고 엔진만 바꾼다.
서술(AI)이 "금화 열 닢을 받았다"고 써도 돈은 늘지 않는다. 돈이 바뀌는 길은 선언한 행동(사기, 팔기, 건네기)과
퀘스트의 보상뿐이다.

  - 시작 돈: 캐릭터가 시트를 받을 때 함께 받는다. 판의 시작 돈에 프리젠의 돈을 더한 것이다.
    처음 시작할 때도, 죽은 캐릭터의 뒤를 이을 새 캐릭터가 들어올 때도 같다. 앞 캐릭터의 돈을 물려받지 않는다.
  - 한 캐릭터는 MONEY_MAX 까지 갖는다. 0 아래로 내려가지 않는다. 넘거나 모자라면 거절한다. 조용히 자르지 않는다.
  - 화폐가 없는 판에서는 늘 0 이다.

DB 를 모른다. 이미 읽어 온 시트와 판을 받아 시트의 돈을 고친다. 저장은 부르는 쪽이 한다.
"""

from app.assets.models import MONEY_MAX
from app.assets.scenarios.snapshot import CurrencySnapshot, Snapshot
from app.tables.errors import Conflict, TableConflictError
from app.tables.models import TableSheet


def starting_money(snapshot: Snapshot, pregen_index: int | None) -> int:
    """
    캐릭터 하나가 시작할 때 받는 돈. 판의 시작 돈에 고른 프리젠의 돈을 더한다. 상한을 넘으면 상한까지다.

    화폐가 없는 판이면 0 이다. 프리젠의 돈은 화폐가 있어야 게시된다(currency_missing).
    """
    if snapshot.currency is None:
        return 0
    total = snapshot.currency.starting
    if pregen_index is not None:
        total += snapshot.pregens[pregen_index].money
    return min(total, MONEY_MAX)


def endow(sheet: TableSheet, snapshot: Snapshot, pregen_index: int | None) -> None:
    """방금 받은 시트에 시작 돈을 준다. 시트를 준 바로 뒤에 부른다."""
    sheet.money = starting_money(snapshot, pregen_index)


def room_for(sheet: TableSheet) -> int:
    """이 캐릭터가 더 받을 수 있는 돈."""
    return MONEY_MAX - sheet.money


def add_money(sheet: TableSheet, amount: int) -> int:
    """
    이 캐릭터에게 돈을 amount 만큼 준다. 준 뒤의 돈을 돌려준다.

    상한을 넘으면 TableConflictError(too_much_money). 아무것도 바꾸지 않는다.
    """
    if amount > room_for(sheet):
        raise TableConflictError(Conflict.TOO_MUCH_MONEY)
    sheet.money += amount
    return sheet.money


def add_up_to(sheet: TableSheet, amount: int) -> int:
    """
    이 캐릭터에게 돈을 amount 까지 준다. 상한에 닿으면 거기까지만 준다. 준 돈을 돌려준다.

    퀘스트의 보상처럼 여럿에게 한꺼번에 주는 것에 쓴다. 한 사람이 가득 찼다고 모두의 보상을 막지 않는다.
    """
    given = min(amount, room_for(sheet))
    sheet.money += given
    return given


def remove_money(sheet: TableSheet, amount: int) -> int:
    """
    이 캐릭터에게서 돈을 amount 만큼 뺀다. 뺀 뒤의 돈을 돌려준다.

    가진 것보다 많으면 TableConflictError(not_enough_money). 아무것도 바꾸지 않는다.
    """
    if amount > sheet.money:
        raise TableConflictError(Conflict.NOT_ENOUGH_MONEY)
    sheet.money -= amount
    return sheet.money


def buying_price(price: int, count: int) -> int:
    """상인에게서 count 개를 살 때 내는 돈. 물건의 값 × 개수다."""
    return price * count


def selling_price(currency: CurrencySnapshot, price: int, count: int) -> int:
    """
    상인에게 count 개를 팔 때 받는 돈. 하나의 값에 화폐의 백분율을 곱해 내림하고 개수를 곱한다.

    하나씩 내림한다. 한 번에 팔든 나눠 팔든 받는 돈이 같다.
    """
    return price * currency.sell_percent // 100 * count


def money_text(currency: CurrencySnapshot, amount: int) -> str:
    """돈을 사람이 읽는 글로. 예: 금화 1,200닢. 단위가 없으면 금화 1,200"""
    return f'{currency.name} {amount:,}{currency.unit}'
