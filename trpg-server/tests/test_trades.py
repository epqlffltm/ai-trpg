# trpg-server/tests/test_trades.py

"""
돈과 거래(#278, app/rounds/trades.py)를 API 로 검증한다. 작은 규칙들은 tests/test_money.py 에 있다.

판: 금화(단위 닢), 시작 돈 30, 사 주는 값 50%. 치유 물약은 10, 늑대 가죽은 9 에 판다. 등불은 값이 없다.
상인(한스, 호칭 상인)은 등불을 장비로 걸치고 물약 4 개와 가죽 1 개를 소지품으로 지닌다. 드워프는 상인이 아니다.
모두 늑대 가죽 2 개와 등불 1 개를 가지고 시작한다.

보는 것.
  - 보이기: 테이블의 화폐와 물건의 값, 시트의 돈, 장면의 상인과 그가 지닌 것의 값.
  - 사기와 팔기: 돈과 소지품과 상인의 재고가 함께 옮겨진다. 결과와 이벤트(item_traded)가 남는다.
  - 받을 때 거절하는 것: 화폐가 없는 판, 사 주지 않는 판, 값이 없는 물건, 상인이 아닌 인물, 장면에 없는 인물,
    적대하는 상인, 모자라는 재고와 돈과 소지품.
  - 차례: 앞사람이 재고를 사 가면 뒷사람은 사지 못한다(아무것도 바뀌지 않는다).
  - 돈 건네기: 받는 사람에게 옮겨진다. 이벤트(money_paid)가 남는다.
  - 게시: 화폐 없이 돈을 쓰는 칸이 있으면 게시하지 못한다(currency_missing).
  - 서술: 거래의 줄과 가진 돈이 서술자에게 간다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from tests.narration_model import asset_body
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token
from tests.test_table_items import kill

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
GOLD = {'name': '금화', 'unit': '닢', 'starting': 30, 'sell_percent': 50}
OPENING = '시장이다. 상인이 짐을 푼다. 망치를 멘 사내가 지나간다.'
BUY = '상인에게 물건을 산다.'
NOT_IN_SCENE = 'action.npc 가 이번 장면의 인물이 아니거나 다른 장소에 있습니다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(user_id)))}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


async def post(client: AsyncClient, url: str, headers: dict, **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def table_url(world: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{world["table"]["id"]}{path}'


async def make_lore(client: AsyncClient, me: dict) -> dict:
    """상인 한스(호칭 상인), 드워프(호칭 망치), 물건 셋(치유 물약, 늑대 가죽, 등불), 사건 하나가 든 로어북과 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='시장의 사람들')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str, keywords: list[str] | None = None) -> dict:
        return await post(client, url, me, name=name, keywords=keywords or [], content=f'{name}의 설정', kind=kind)

    return {
        'lorebook': lorebook,
        'hans': await entry('한스', 'person', ['상인']),
        'dwarf': await entry('드워프', 'person', ['망치']),
        'potion': await entry('치유 물약', 'item'),
        'pelt': await entry('늑대 가죽', 'item'),
        'lamp': await entry('등불', 'item'),
        'hunt': await entry('늑대 사냥', 'event'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


def merchant_sheet(lore: dict, **fields) -> dict:
    """한스의 시트. 등불을 걸치고 물약 4 개와 가죽 1 개를 판다."""
    sheet = {
        'entry_id': lore['hans']['id'],
        'sheet': SHEET,
        'merchant': True,
        'equipment': [{'entry_id': lore['lamp']['id']}],
        'inventory': [{'entry_id': lore['potion']['id'], 'count': 4}, {'entry_id': lore['pelt']['id'], 'count': 1}],
    }
    return {**sheet, **fields}


def scenario_body(lore: dict, **fields) -> dict:
    body = {
        'title': '시장',
        'rulebook_id': lore['rulebook']['id'],
        'lorebook_ids': [lore['lorebook']['id']],
        'openings': [OPENING],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'items': [
            {'entry_id': lore['potion']['id'], 'kind': 'consumable', 'heals': 'light', 'price': 10},
            {'entry_id': lore['pelt']['id'], 'kind': 'gear', 'price': 9},
        ],
        'starting_items': [{'entry_id': lore['pelt']['id'], 'count': 2}, {'entry_id': lore['lamp']['id'], 'count': 1}],
        'currency': GOLD,
        'npc_sheets': [merchant_sheet(lore)],
    }
    return {**body, **fields}


async def start(client: AsyncClient, me: dict, *others: dict, merchant: dict | None = None, **fields) -> dict:
    """
    시장의 판으로 테이블을 시작한다. 나(기사)와 others(약사)가 앉는다.

    fields 로 시나리오의 칸을, merchant 로 한스의 시트의 칸을 바꾼다.
    """
    lore = await make_lore(client, me)
    if merchant is not None:
        fields['npc_sheets'] = [merchant_sheet(lore, **merchant)]
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(lore, **fields))
    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    world = {**lore, 'table': table}
    for headers, name in zip([me, *others], ['기사', '약사'], strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(world, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(world, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return world


def buy(world: dict, item: str, count: int = 1, npc: str = 'hans') -> dict:
    return {'kind': 'buy', 'npc': world[npc]['id'], 'item': world[item]['id'], 'count': count}


def sell(world: dict, item: str, count: int = 1, npc: str = 'hans') -> dict:
    return {'kind': 'sell', 'npc': world[npc]['id'], 'item': world[item]['id'], 'count': count}


def pay(target: uuid.UUID, amount: int) -> dict:
    return {'kind': 'pay', 'target': str(target), 'amount': amount}


async def send(client: AsyncClient, headers: dict, world: dict, action: dict, content: str = BUY):
    body = {'content': content, 'action': action}
    return await client.put(table_url(world, '/rounds/current/declaration'), json=body, headers=headers)


async def declare(client: AsyncClient, headers: dict, world: dict, action: dict, content: str = BUY) -> None:
    response = await send(client, headers, world, action, content)
    assert response.status_code == status.HTTP_200_OK, response.text


async def outcome_of(client: AsyncClient, me: dict, world: dict, user_id: uuid.UUID = ME) -> dict:
    response = await client.get(table_url(world, '/rounds/1'), headers=me)
    return next(item for item in response.json()['declarations'] if item['user_id'] == str(user_id))['outcome']


async def sheet_of(client: AsyncClient, me: dict, world: dict, user_id: uuid.UUID = ME) -> dict:
    detail = (await client.get(table_url(world), headers=me)).json()
    return next(member for member in detail['members'] if member['user_id'] == str(user_id))['sheet']


def held(sheet: dict) -> list[tuple[str, int]]:
    return [(item['name'], item['count']) for item in sheet['items']]


async def merchant_goods(client: AsyncClient, me: dict, world: dict) -> list[tuple[str, int, bool, int | None]]:
    people = (await client.get(table_url(world, '/rounds/current/people'), headers=me)).json()['people']
    hans = next(person for person in people if person['id'] == world['hans']['id'])
    return [(item['name'], item['count'], item['equipped'], item['price']) for item in hans['items']]


async def events_of(client: AsyncClient, headers: dict, world: dict, type_: str) -> list[dict]:
    response = await client.get(table_url(world, '/events'), params={'limit': 100}, headers=headers)
    return [event for event in response.json()['items'] if event['type'] == type_]


# --- 보이기 ---


async def test_the_table_shows_the_currency_the_prices_and_the_money(client: AsyncClient, me: dict):
    world = await start(client, me)

    detail = (await client.get(table_url(world), headers=me)).json()

    assert detail['currency'] == {'name': '금화', 'unit': '닢', 'sell_percent': 50}
    assert {item['name']: item['price'] for item in detail['items']} == {'치유 물약': 10, '늑대 가죽': 9, '등불': None}
    assert (await sheet_of(client, me, world))['money'] == 30


async def test_the_scene_shows_the_merchant_and_its_prices(client: AsyncClient, me: dict):
    world = await start(client, me)

    people = (await client.get(table_url(world, '/rounds/current/people'), headers=me)).json()['people']

    assert {person['name']: person['merchant'] for person in people} == {'상인': True, '망치': False}
    assert await merchant_goods(client, me, world) == [
        ('등불', 1, True, None),
        ('치유 물약', 4, False, 10),
        ('늑대 가죽', 1, False, 9),
    ]


async def test_a_pregen_brings_its_own_money(client: AsyncClient, me: dict):
    lore_fields = {'pregens': [{'name': '부자', 'sheet': SHEET, 'money': 70}], 'character_modes': ['pregen']}
    lore = await make_lore(client, me)
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(lore, **lore_fields))
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    world = {**lore, 'table': table}
    await client.put(table_url(world, '/character'), json={'pregen_index': 0}, headers=me)
    await client.post(table_url(world, '/start'), headers=me)

    assert (await sheet_of(client, me, world))['money'] == 100


async def test_a_new_character_starts_with_fresh_money(client: AsyncClient, me: dict, session: AsyncSession, narrated):
    world = await start(client, me)
    await declare(client, me, world, buy(world, 'potion', 3))
    await narrated()
    await kill(session, ME)

    arrived = await client.post(table_url(world, '/character'), json={'name': '새 기사'}, headers=me)

    assert arrived.status_code == status.HTTP_201_CREATED, arrived.text
    # 앞 캐릭터의 남은 돈(0)을 물려받지 않고 시작 돈을 새로 받는다
    assert (await sheet_of(client, me, world))['money'] == 30


# --- 사기와 팔기 ---


async def test_buying_pays_the_price_and_takes_from_the_stock(client: AsyncClient, me: dict, narrated):
    world = await start(client, me)

    await declare(client, me, world, buy(world, 'potion', 2))
    await narrated()

    assert (await outcome_of(client, me, world))['trade'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'side': 'buy',
        'npc_id': world['hans']['id'],
        'npc_name': '상인',
        'entry_id': world['potion']['id'],
        'name': '치유 물약',
        'count': 2,
        'price': 20,
        'traded': True,
        'reason': None,
        'total': 2,
        'money': 10,
    }
    sheet = await sheet_of(client, me, world)
    assert (sheet['money'], held(sheet)) == (10, [('치유 물약', 2), ('늑대 가죽', 2), ('등불', 1)])
    assert ('치유 물약', 2, False, 10) in await merchant_goods(client, me, world)


async def test_selling_gets_half_the_price_and_the_thing_is_gone(client: AsyncClient, me: dict, narrated):
    world = await start(client, me)

    await declare(client, me, world, sell(world, 'pelt', 2), content='상인에게 가죽을 판다.')
    await narrated()

    trade = (await outcome_of(client, me, world))['trade']
    assert (trade['side'], trade['price'], trade['traded'], trade['total'], trade['money']) == ('sell', 8, True, 0, 38)
    sheet = await sheet_of(client, me, world)
    assert (sheet['money'], held(sheet)) == (38, [('등불', 1)])
    # 판 가죽은 상인의 재고가 되지 않는다
    assert ('늑대 가죽', 1, False, 9) in await merchant_goods(client, me, world)


async def test_a_trade_is_recorded(client: AsyncClient, me: dict, narrated):
    world = await start(client, me)

    await declare(client, me, world, buy(world, 'pelt'))
    await narrated()

    (traded,) = await events_of(client, me, world, 'item_traded')
    assert traded['actor_id'] is None
    assert {key: traded['payload'][key] for key in ('round', 'side', 'name', 'count', 'price', 'money')} == {
        'round': 1,
        'side': 'buy',
        'name': '늑대 가죽',
        'count': 1,
        'price': 9,
        'money': 21,
    }


async def test_the_second_buyer_finds_the_stock_gone(client: AsyncClient, me: dict, friend: dict, narrated):
    world = await start(client, me, friend)

    await declare(client, me, world, buy(world, 'potion', 3))
    await declare(client, friend, world, buy(world, 'potion', 2))
    await narrated()

    first = (await outcome_of(client, me, world))['trade']
    second = (await outcome_of(client, me, world, FRIEND))['trade']
    assert (first['traded'], first['money']) == (True, 0)
    assert (second['traded'], second['reason'], second['money'], second['total']) == (False, 'out_of_stock', 30, 0)
    assert ('치유 물약', 1, False, 10) in await merchant_goods(client, me, world)


@pytest.mark.parametrize(
    ('action', 'code', 'detail'),
    [
        (lambda world: buy(world, 'lamp'), 422, 'action.item 가 이 테이블의 규칙에 없습니다.'),
        (lambda world: sell(world, 'lamp'), 422, 'action.item 가 이 테이블의 규칙에 없습니다.'),
        (lambda world: buy(world, 'potion', npc='dwarf'), 409, 'not_merchant'),
        (lambda world: {**buy(world, 'potion'), 'npc': str(uuid.uuid4())}, 422, NOT_IN_SCENE),
        (lambda world: buy(world, 'potion', 5), 409, 'out_of_stock'),
        (lambda world: buy(world, 'pelt', 2), 409, 'out_of_stock'),
        (lambda world: buy(world, 'potion', 4), 409, 'not_enough_money'),
        (lambda world: sell(world, 'potion'), 409, 'item_not_held'),
        (lambda world: sell(world, 'pelt', 3), 409, 'item_not_held'),
        (lambda world: pay(ME, 1), 422, 'action.target 이 이 테이블에 앉은 사람이 아닙니다.'),
        (lambda world: pay(uuid.uuid4(), 1), 422, 'action.target 이 이 테이블에 앉은 사람이 아닙니다.'),
    ],
)
async def test_what_cannot_be_traded_is_refused(client: AsyncClient, me: dict, action, code: int, detail: str):
    world = await start(client, me)

    response = await send(client, me, world, action(world))

    assert response.status_code == code
    assert detail in (response.json().get('detail'), response.json().get('reason'))


@pytest.mark.parametrize('action', [lambda world: buy(world, 'potion'), lambda world: sell(world, 'pelt')])
async def test_a_hostile_merchant_does_not_trade(client: AsyncClient, me: dict, action):
    world = await start(client, me, merchant={'attitude': 'hostile'})

    response = await send(client, me, world, action(world))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'merchant_unavailable'


async def test_without_a_currency_nothing_is_traded(client: AsyncClient, me: dict):
    world = await start(client, me, currency=None, items=[], npc_sheets=[])

    for action in (buy(world, 'potion'), sell(world, 'pelt'), pay(FRIEND, 1)):
        response = await send(client, me, world, action)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()['detail'] == 'action.kind 가 이 테이블의 규칙에 없습니다.'
    assert (await sheet_of(client, me, world))['money'] == 0


async def test_a_merchant_does_not_buy_back_when_the_scenario_says_so(client: AsyncClient, me: dict):
    world = await start(client, me, currency={**GOLD, 'sell_percent': 0})

    response = await send(client, me, world, sell(world, 'pelt'))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'] == 'action.kind 가 이 테이블의 규칙에 없습니다.'


async def test_money_that_would_go_over_the_cap_cannot_be_earned(client: AsyncClient, me: dict):
    world = await start(client, me, currency={**GOLD, 'starting': 999_999})

    # 가죽 둘을 팔면 8 을 받는다. 상한(1,000,000)까지 1 이 남았다
    response = await send(client, me, world, sell(world, 'pelt', 2))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'too_much_money'


# --- 돈 건네기 ---


async def test_paying_moves_the_money(client: AsyncClient, me: dict, friend: dict, narrated):
    world = await start(client, me, friend)

    await declare(client, me, world, pay(FRIEND, 12), content='약사에게 돈을 건넨다.')
    await declare(client, friend, world, buy(world, 'potion'))
    await narrated()

    assert (await outcome_of(client, me, world))['pay'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'amount': 12,
        'paid': True,
        'reason': None,
        'target': {'user_id': str(FRIEND), 'character_name': '약사'},
        'remaining': 18,
        'target_total': 42,
    }
    # 약사는 받은 뒤에 물약을 샀다
    assert (await sheet_of(client, me, world, FRIEND))['money'] == 32
    (paid,) = await events_of(client, me, world, 'money_paid')
    assert (paid['payload']['amount'], paid['payload']['paid']) == (12, True)


async def test_more_money_than_held_cannot_be_paid(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)

    response = await send(client, me, world, pay(FRIEND, 31))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_enough_money'


# --- 게시 ---


# 돈을 쓰는 칸 하나씩. 나머지 돈의 칸은 비운다
MONEY_FIELDS = {
    'price': lambda lore: {'npc_sheets': []},
    'merchant': lambda lore: {'items': []},
    'pregen': lambda lore: {
        'items': [],
        'npc_sheets': [],
        'pregens': [{'name': '부자', 'sheet': SHEET, 'money': 5}],
    },
    'quest': lambda lore: {
        'items': [],
        'npc_sheets': [],
        'quests': [{'entry_id': lore['hunt']['id'], 'reward_money': 5}],
    },
}


@pytest.mark.parametrize('field', list(MONEY_FIELDS))
async def test_money_without_a_currency_is_not_published(client: AsyncClient, me: dict, field: str):
    lore = await make_lore(client, me)
    fields = MONEY_FIELDS[field](lore)
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(lore, currency=None, **fields))

    response = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()['problems'] == ['currency_missing']


async def test_a_scenario_without_money_needs_no_currency(client: AsyncClient, me: dict):
    lore = await make_lore(client, me)
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(lore, currency=None, items=[], npc_sheets=[]))

    response = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()['snapshot']['currency'] is None


async def test_the_currency_is_frozen_in_the_version(client: AsyncClient, me: dict):
    lore = await make_lore(client, me)
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(lore))

    response = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)

    snapshot = response.json()['snapshot']
    assert snapshot['currency'] == GOLD
    assert snapshot['npc_sheets'][0]['merchant'] is True
    assert [rule['price'] for rule in snapshot['items']] == [10, 9]


async def test_the_currency_is_saved_and_cleared(client: AsyncClient, me: dict):
    lore = await make_lore(client, me)
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(lore))
    assert scenario['currency'] == GOLD

    cleared = await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'currency': None}, headers=me)

    assert cleared.json()['currency'] is None


# --- 서술 ---


async def test_the_narrator_hears_the_trade_and_the_money(client: AsyncClient, me: dict, narrated):
    world = await start(client, me)

    await declare(client, me, world, buy(world, 'potion', 2))
    await narrated()

    # 가짜 서술자는 받은 것을 그대로 늘어놓는다
    scene = (await client.get(table_url(world, '/rounds/current'), headers=me)).json()['scene']
    assert '(산 물건: 상인 에게서 치유 물약 2개. 금화 20닢을(를) 냈다)' in scene
    assert '[소지금: 금화 10닢]' in scene
