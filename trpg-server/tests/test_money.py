# trpg-server/tests/test_money.py

"""
돈(#278)의 작은 규칙들을 검증한다. DB 를 쓰지 않는다. 거래를 API 로 보는 것은 tests/test_trades.py 다.

보는 것.
  - 시나리오의 화폐의 모양. 판의 형식 46: 돈을 쓰는 칸은 화폐가 있어야 하고, 옛 판은 돈이 없는 판으로 읽는다.
  - 캐릭터의 돈: 시작 돈(판 + 프리젠, 상한), 더하기와 빼기(상한과 0), 보상처럼 상한까지 주기.
  - 값: 살 때는 값 × 개수, 팔 때는 하나의 값에 백분율을 곱해 내림한 것 × 개수. 돈의 글.
  - 퀘스트의 돈의 보상: 살아 있는 캐릭터마다, 상한에 닿으면 거기까지.
  - 거래를 다시 볼 때의 까닭의 차례, 서술의 줄, 기록의 줄.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.assets.models import MONEY_MAX, NpcAttitude
from app.assets.scenarios.schemas import Currency, ItemRule, NpcSheet, Pregen, QuestRule
from app.assets.scenarios.snapshot import CurrencySnapshot, NpcSheetSnapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_45
from app.engine.action import BuyAction, PayAction, SellAction
from app.events.models import EventType, TableEvent
from app.rounds import prompt, trades
from app.rounds.cast import CastMember
from app.rounds.move_lines import describe_move, describe_pay, describe_trade
from app.rounds.narrator import Move, NarrationRequest, PayNote, TradeNote
from app.tables import money, quests
from app.tables.errors import TableConflictError
from app.tables.models import NpcStatus, TableItem, TableNpc, TableNpcItem, TableSheet
from app.transcripts.labels import Labels
from app.transcripts.markdown import render_event
from tests.sheets import SHEET

GOLD = CurrencySnapshot(name='금화', unit='닢', starting=30, sell_percent=50)
POTION = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000001')
PELT = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000002')
HANS = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000003')


def sheet_with(amount: int = 0, *held: tuple[uuid.UUID, int]) -> TableSheet:
    return TableSheet(money=amount, items=[TableItem(entry_id=entry_id, count=count) for entry_id, count in held])


def member_with(sheet: TableSheet, dead: bool = False) -> SimpleNamespace:
    sheet.died_at = datetime(2026, 10, 24, tzinfo=UTC) if dead else None
    return SimpleNamespace(user_id=uuid.uuid4(), character_name='기사', sheet=sheet)


# --- 시나리오의 화폐와 판 ---


@pytest.mark.parametrize(
    'body',
    [
        {'name': ''},
        {'name': '금화', 'sell_percent': 101},
        {'name': '금화', 'sell_percent': -1},
        {'name': '금화', 'starting': MONEY_MAX + 1},
        {'name': '금화', 'unit': '닢' * 11},
        {'name': '금화', 'rate': 2},
    ],
)
def test_a_wrong_currency_is_refused(body: dict):
    with pytest.raises(ValidationError):
        Currency.model_validate(body)


def test_a_currency_starts_with_nothing_and_buys_back_at_half():
    assert Currency(name='금화') == Currency(name='금화', unit='', starting=0, sell_percent=50)


@pytest.mark.parametrize(
    ('model', 'body'),
    [
        (ItemRule, {'entry_id': str(POTION), 'price': 0}),
        (ItemRule, {'entry_id': str(POTION), 'price': MONEY_MAX + 1}),
        (Pregen, {'name': '약사', 'money': -1}),
        (QuestRule, {'entry_id': str(POTION), 'reward_money': MONEY_MAX + 1}),
    ],
)
def test_wrong_amounts_are_refused(model, body: dict):
    with pytest.raises(ValidationError):
        model.model_validate(body)


def test_nothing_costs_money_unless_written():
    assert ItemRule(entry_id=POTION).price is None
    assert Pregen(name='약사').money == 0
    assert QuestRule(entry_id=POTION).reward_money == 0
    assert NpcSheet(entry_id=HANS, sheet=SHEET).merchant is False


def test_an_old_snapshot_has_no_money():
    document = {
        'format': 45,
        'items': [{'entry_id': str(POTION), 'kind': 'gear'}],
        'pregens': [{'name': '약사', 'description': '', 'sheet': SHEET, 'items': []}],
        'quests': [{'entry_id': str(PELT), 'reward': []}],
        'npc_sheets': [{'entry_id': str(HANS), 'sheet': SHEET}],
    }

    upgraded = upgrade_from_45(document)

    assert upgraded['format'] == 46
    assert upgraded['currency'] is None
    assert upgraded['items'][0]['price'] is None
    assert upgraded['pregens'][0]['money'] == 0
    assert upgraded['quests'][0]['reward_money'] == 0
    assert upgraded['npc_sheets'][0]['merchant'] is False
    assert 'price' not in document['items'][0]
    assert UPGRADES[45] is upgrade_from_45


# --- 캐릭터의 돈 ---


def snapshot_of(currency: CurrencySnapshot | None, *pregen_money: int) -> SimpleNamespace:
    return SimpleNamespace(currency=currency, pregens=[SimpleNamespace(money=amount) for amount in pregen_money])


def test_the_starting_money_adds_the_pregen_s():
    snapshot = snapshot_of(GOLD, 0, 25)

    assert money.starting_money(snapshot, None) == 30
    assert money.starting_money(snapshot, 0) == 30
    assert money.starting_money(snapshot, 1) == 55


def test_the_starting_money_stops_at_the_cap():
    rich = GOLD.model_copy(update={'starting': MONEY_MAX})

    assert money.starting_money(snapshot_of(rich, 1), 0) == MONEY_MAX


def test_without_a_currency_nobody_has_money():
    assert money.starting_money(snapshot_of(None, 25), 0) == 0


def test_a_new_sheet_is_given_its_starting_money():
    sheet = TableSheet()

    money.endow(sheet, snapshot_of(GOLD, 25), 0)

    assert sheet.money == 55


def test_money_is_added_up_to_the_cap_only():
    sheet = sheet_with(MONEY_MAX - 5)

    with pytest.raises(TableConflictError):
        money.add_money(sheet, 6)

    assert sheet.money == MONEY_MAX - 5
    assert money.add_money(sheet, 5) == MONEY_MAX


def test_money_is_never_taken_below_zero():
    sheet = sheet_with(10)

    with pytest.raises(TableConflictError):
        money.remove_money(sheet, 11)

    assert sheet.money == 10
    assert money.remove_money(sheet, 10) == 0


def test_a_reward_fills_up_to_the_cap():
    sheet = sheet_with(MONEY_MAX - 3)

    assert money.add_up_to(sheet, 10) == 3
    assert sheet.money == MONEY_MAX


def test_buying_costs_the_price_times_the_count():
    assert money.buying_price(10, 3) == 30


@pytest.mark.parametrize(('percent', 'gain'), [(50, 6), (100, 15), (0, 0), (34, 3)])
def test_selling_rounds_down_each_one(percent: int, gain: int):
    currency = GOLD.model_copy(update={'sell_percent': percent})

    # 하나의 값 5 에 백분율을 곱해 내림한 것 × 3 개
    assert money.selling_price(currency, 5, 3) == gain


@pytest.mark.parametrize(
    ('currency', 'text'),
    [(GOLD, '금화 1,200닢'), (GOLD.model_copy(update={'unit': ''}), '금화 1,200')],
)
def test_money_reads_in_the_currency(currency: CurrencySnapshot, text: str):
    assert money.money_text(currency, 1200) == text


# --- 퀘스트의 돈의 보상 ---


def quest_with(reward_money: int) -> quests.CatalogQuest:
    return quests.CatalogQuest(entry_id=PELT, name='늑대 사냥', start='active', reward=[], reward_money=reward_money)


def test_every_living_character_gets_the_reward_money():
    alive, near_cap, dead = sheet_with(5), sheet_with(MONEY_MAX - 2), sheet_with(0)
    members = [member_with(alive), member_with(near_cap), member_with(dead, dead=True)]
    table = SimpleNamespace(id=uuid.uuid4(), members=members)

    rewards = quests.give_rewards(table, quest_with(10), {})

    assert [reward['money'] for reward in rewards] == [
        {'count': 10, 'total': 15, 'capped': False},
        {'count': 2, 'total': MONEY_MAX, 'capped': True},
    ]
    assert dead.money == 0


def test_a_quest_without_rewards_gives_nothing():
    table = SimpleNamespace(id=uuid.uuid4(), members=[member_with(sheet_with(5))])

    assert quests.give_rewards(table, quest_with(0), {}) == []


# --- 차례가 왔을 때 다시 보기 ---


def merchant(status: NpcStatus = NpcStatus.ALIVE, attitude: NpcAttitude = NpcAttitude.NEUTRAL, stock: int = 3):
    definition = NpcSheetSnapshot(
        entry_id=HANS,
        sheet=SHEET,
        merchant=True,
        equipment=[{'entry_id': PELT, 'count': 1, 'chance': 100}],
        inventory=[{'entry_id': POTION, 'count': 3, 'chance': 100}],
    )
    npc = TableNpc(entry_id=HANS, status=status, attitude=attitude, items=[TableNpcItem(slot=1, count=stock)])
    return CastMember(entry_id=HANS, name='상인', npc=npc, definition=definition)


@pytest.mark.parametrize(
    ('seller', 'cash', 'held', 'reason'),
    [
        (merchant(status=NpcStatus.DOWNED, stock=0), 0, 99, trades.Reason.UNAVAILABLE),
        (merchant(attitude=NpcAttitude.HOSTILE), 100, 0, trades.Reason.UNAVAILABLE),
        (merchant(stock=1), 0, 99, trades.Reason.OUT_OF_STOCK),
        (merchant(), 19, 99, trades.Reason.NOT_ENOUGH_MONEY),
        (merchant(), 20, 98, trades.Reason.FULL),
        (merchant(), 20, 97, None),
    ],
)
def test_a_purchase_is_checked_again_in_order(seller: CastMember, cash: int, held: int, reason: str | None):
    buyer = member_with(sheet_with(cash, (POTION, held)))
    action = BuyAction(kind='buy', npc=HANS, item=POTION, count=2)

    assert trades.buy_shortfall(buyer, seller, action, 20) == reason


@pytest.mark.parametrize(
    ('seller', 'held', 'cash', 'reason'),
    [
        (merchant(status=NpcStatus.DEAD), 0, MONEY_MAX, trades.Reason.UNAVAILABLE),
        (merchant(), 1, MONEY_MAX, trades.Reason.NOT_HELD),
        (merchant(), 2, MONEY_MAX - 7, trades.Reason.TOO_MUCH_MONEY),
        (merchant(), 2, MONEY_MAX - 8, None),
    ],
)
def test_a_sale_is_checked_again_in_order(seller: CastMember, held: int, cash: int, reason: str | None):
    owner = member_with(sheet_with(cash, (PELT, held)))
    action = SellAction(kind='sell', npc=HANS, item=PELT, count=2)

    assert trades.sell_shortfall(owner, seller, action, 8) == reason


@pytest.mark.parametrize(
    ('cash', 'recipient', 'reason'),
    [
        (9, member_with(sheet_with(0)), trades.Reason.NOT_ENOUGH_MONEY),
        (10, None, trades.Reason.TARGET_GONE),
        (10, member_with(sheet_with(MONEY_MAX - 9)), trades.Reason.TOO_MUCH_MONEY),
        (10, member_with(sheet_with(MONEY_MAX - 10)), None),
    ],
)
def test_a_payment_is_checked_again_in_order(cash: int, recipient, reason: str | None):
    payer = member_with(sheet_with(cash))
    action = PayAction(kind='pay', target=uuid.uuid4(), amount=10)

    assert trades.pay_shortfall(payer, recipient, action) == reason


def test_a_merchant_sells_only_what_it_carries_in_its_pack():
    seller = merchant()

    assert trades.stock_of(seller, POTION).count == 3
    # 장비로 걸친 가죽은 팔지 않는다
    assert trades.stock_of(seller, PELT) is None


def test_someone_without_a_merchant_sheet_does_not_trade():
    assert not trades.is_merchant(CastMember(entry_id=HANS, name='상인', npc=TableNpc(), definition=None))


# --- 서술과 기록 ---


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (
            TradeNote('buy', '상인', '치유 물약', 2, '금화 20닢', True),
            '(산 물건: 상인 에게서 치유 물약 2개. 금화 20닢을(를) 냈다)',
        ),
        (
            TradeNote('sell', '상인', '늑대 가죽', 3, '금화 6닢', True),
            '(판 물건: 상인 에게 늑대 가죽 3개. 금화 6닢을(를) 받았다)',
        ),
        (
            TradeNote('buy', '상인', '치유 물약', 2, '금화 20닢', False, 'out_of_stock'),
            '(사려던 물건: 상인 에게서 치유 물약 2개(금화 20닢). 상인에게 그만큼이 없었다)',
        ),
        (
            TradeNote('sell', '상인', '늑대 가죽', 3, '금화 6닢', False, 'unavailable'),
            '(팔려던 물건: 상인 에게 늑대 가죽 3개(금화 6닢). 상인이 거래할 수 없었다)',
        ),
    ],
)
def test_the_trade_line(note: TradeNote, line: str):
    assert describe_trade(note) == line


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (PayNote('금화 10닢', '영애', True), '(건넨 돈: 금화 10닢 → 영애)'),
        (PayNote('금화 10닢', None, False, 'target_gone'), '(건네려던 돈: 금화 10닢. 받을 사람이 없었다)'),
    ],
)
def test_the_pay_line(note: PayNote, line: str):
    assert describe_pay(note) == line


def test_the_money_held_goes_with_the_move():
    move = Move(character_name='기사', content='산다.', money='금화 10닢')

    assert describe_move(move) == '기사: 산다. [소지금: 금화 10닢]'


def request_with(*moves: Move) -> NarrationRequest:
    return NarrationRequest(round_number=1, scene='시장이다.', moves=list(moves))


def test_the_narrator_is_told_how_to_treat_money_only_when_there_is_money():
    with_money = prompt.round_text(request_with(Move(character_name='기사', content='산다.', money='금화 10닢')))
    without = prompt.round_text(request_with(Move(character_name='기사', content='산다.')))

    assert prompt.MONEY_NOTE in with_money
    assert prompt.MONEY_NOTE not in without


def labels_with(name: str = '금화', unit: str = '닢') -> Labels:
    return Labels(currency_name=name, currency_unit=unit)


def event(type_: EventType, payload: dict) -> TableEvent:
    return TableEvent(type=type_, payload=payload)


@pytest.mark.parametrize(
    ('payload', 'text'),
    [
        ({'side': 'buy', 'traded': True}, '기사 · 상인: 치유 물약 2개 삼 (금화 1,200닢)'),
        ({'side': 'sell', 'traded': False}, '기사 · 상인: 치유 물약 2개 팖 (금화 1,200닢) (하지 못함)'),
    ],
)
def test_a_trade_is_written_in_the_currency(payload: dict, text: str):
    trade = {'character_name': '기사', 'npc_name': '상인', 'name': '치유 물약', 'count': 2, 'price': 1200, **payload}

    assert text in render_event(event(EventType.ITEM_TRADED, trade), labels_with())


def test_a_payment_is_written_in_the_currency():
    paid = {'character_name': '기사', 'amount': 10, 'paid': True, 'target': {'character_name': '약사'}}

    assert '기사 → 약사: 금화 10닢' in render_event(event(EventType.MONEY_PAID, paid), labels_with())
    assert '기사 → 약사: 10' in render_event(event(EventType.MONEY_PAID, paid), Labels())
