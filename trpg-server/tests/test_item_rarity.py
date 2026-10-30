# trpg-server/tests/test_item_rarity.py

"""
물건의 등급(#456, app/assets/models.py 의 ItemRarity)을 검증한다. 노말, 레어, 유니크, 에픽, 레전드의 차례다.

시나리오는 test_scenario_items.py 의 것이다. 로어북에 물약과 밧줄이 있다.

보는 것.
  - 시나리오: 아이템 규칙에 등급을 적고 판에 굳힌다. 종류를 비우면 장비다. 모르는 등급은 거부한다.
    규칙이 없는 물건과 옛 판의 물건은 노말이다(판 형식 35).
  - 테이블: 판의 물건 목록에 등급이 실린다(test_table_items.py).
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token

from app.assets.models import RARITY_ORDER, ItemRarity
from app.assets.scenarios.snapshot import Snapshot, item_rule_of, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_34
from app.tables import items
from tests.narration_model import with_model
from tests.test_npc_sheets import add_entry, post, published
from tests.test_scenario_items import LOREBOOKS_URL, ME, SCENARIOS_URL, rule, scenario_with

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """물건 둘(물약, 밧줄)이 든 로어북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='모험의 물건들')
    return {
        'lorebook': lorebook,
        'potion': await add_entry(client, me, lorebook, '치유 물약', 'item'),
        'rope': await add_entry(client, me, lorebook, '밧줄', 'item'),
    }


async def test_a_rarity_is_saved_and_published(client: AsyncClient, me: dict[str, str], lore: dict):
    rules = [
        {'entry_id': lore['rope']['id'], 'rarity': 'epic'},
        rule(lore['potion'], effects=[{'kind': 'heal', 'magnitude': 'light'}]),
    ]
    scenario = await scenario_with(client, me, lore, items=rules)

    snapshot = await published(client, me, scenario)

    # 종류를 비우면 장비다. 등급을 비우면 노말이다
    assert scenario['items'] == [
        {
            'entry_id': lore['rope']['id'],
            'kind': 'gear',
            'effects': [],
            'rarity': 'epic',
            'price': None,
            'slots': [],
            'slot_count': 1,
            'attack': None,
            'defense': None,
            'guard': None,
            'ap': None,
            'ward': None,
            'lock': None,
            'throw': None,
            'aids': [],
            'resistances': [],
            'nature': None,
            'trap': None,
        },
        {
            'entry_id': lore['potion']['id'],
            'kind': 'consumable',
            'effects': [{'kind': 'heal', 'magnitude': 'light'}],
            'rarity': 'normal',
            'price': None,
            'slots': [],
            'slot_count': 1,
            'attack': None,
            'defense': None,
            'guard': None,
            'ap': None,
            'ward': None,
            'lock': None,
            'throw': None,
            'aids': [],
            'resistances': [],
            'nature': None,
            'trap': None,
        },
    ]
    assert [item['rarity'] for item in snapshot['items']] == ['epic', 'normal']
    # 테이블은 판의 물건 목록으로 이름과 등급을 찾는다(소지품, 판의 물건 목록, 몬스터가 지닌 것)
    catalog = items.catalog(read_snapshot(snapshot))
    assert (catalog[uuid.UUID(lore['rope']['id'])].rarity, catalog[uuid.UUID(lore['potion']['id'])].rarity) == (
        ItemRarity.EPIC,
        ItemRarity.NORMAL,
    )


async def test_an_unknown_rarity_is_refused(client: AsyncClient, me: dict[str, str], lore: dict):
    body = {'title': '추격전', 'items': [{'entry_id': lore['rope']['id'], 'rarity': 'mythic'}]}

    response = await client.post(SCENARIOS_URL, json=with_model(body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_rarities_go_from_normal_to_legendary():
    assert [rarity.value for rarity in RARITY_ORDER] == ['normal', 'rare', 'unique', 'epic', 'legendary']


def test_a_thing_without_a_rule_is_normal():
    snapshot = Snapshot.model_construct(items=[])

    assert item_rule_of(snapshot, uuid.uuid4()).rarity == ItemRarity.NORMAL


def test_an_old_snapshot_reads_every_thing_as_normal():
    rule_line = {'entry_id': str(uuid.uuid4()), 'kind': 'gear', 'effects': []}
    document = {'format': 34, 'items': [rule_line]}

    upgraded = upgrade_from_34(document)

    assert upgraded['format'] == 35
    assert upgraded['items'] == [{**rule_line, 'rarity': 'normal'}]
    # 받은 문서는 고치지 않는다
    assert 'rarity' not in document['items'][0]
