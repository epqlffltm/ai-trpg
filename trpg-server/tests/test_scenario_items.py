# trpg-server/tests/test_scenario_items.py

"""
시나리오의 아이템: 아이템 규칙, 시작 소지품, 프리젠의 소지품을 검증한다.

셋을 본다.
  - 시나리오: 적고 읽고 고친다. 모양만 본다(장비에 회복의 양 없음, 같은 물건 두 줄 없음, 개수의 범위).
  - 게시: 붙인 로어북의 물건 항목을 가리키는지, 회복의 양이 룰북의 등급인지.
  - 판: 형식 17 에 실린다. 옛 판은 아이템 없이 읽는다. 규칙이 없는 물건은 장비다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.testing.tokens import SigningKey, make_access_claims, make_token

from app.assets.models import ITEM_STACK_MAX, SCENARIO_MAX_STARTING_ITEMS, ItemKind
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, Snapshot, item_entries, item_rule_of, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_16
from app.engine.templates import SRD5
from app.main import API_PREFIX
from tests.narration_model import with_model
from tests.sheets import SHEET
from tests.test_npc_sheets import add_entry, create_scenario, post, published, refused

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만드는 사람이다."""
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """물건 둘(물약, 밧줄)과 인물 하나가 든 로어북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='모험의 물건들')
    return {
        'lorebook': lorebook,
        'potion': await add_entry(client, me, lorebook, '치유 물약', 'item'),
        'rope': await add_entry(client, me, lorebook, '밧줄', 'item'),
        'lady': await add_entry(client, me, lorebook, '악역영애', 'person'),
    }


def rule(entry: dict, kind: str = 'consumable', **fields) -> dict:
    return {'entry_id': entry['id'], 'kind': kind, **fields}


def stack(entry: dict, count: int = 1) -> dict:
    return {'entry_id': entry['id'], 'count': count, 'wear': []}


def pregen(name: str, *items: dict) -> dict:
    return {'name': name, 'description': '', 'sheet': SHEET, 'items': list(items)}


async def scenario_with(client: AsyncClient, me: dict, lore: dict, **fields) -> dict:
    """물건 로어북을 붙이고, 인물에게 줄 기본 NPC 시트를 둔 시나리오."""
    return await create_scenario(client, me, lore, default_npc_sheet=SHEET, **fields)


# --- 시나리오: 적고 읽고 고친다 ---


async def test_items_are_saved_and_read_back(client: AsyncClient, me: dict[str, str], lore: dict):
    items = [rule(lore['potion'], effects=[{'kind': 'heal', 'magnitude': 'light'}]), rule(lore['rope'], 'gear')]
    scenario = await scenario_with(
        client,
        me,
        lore,
        items=items,
        starting_items=[stack(lore['rope'])],
        pregens=[pregen('기사', stack(lore['potion'], 2))],
    )

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    assert read['items'] == [
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
            'treat_bonus': None,
        },
        {
            'entry_id': lore['rope']['id'],
            'kind': 'gear',
            'effects': [],
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
            'treat_bonus': None,
        },
    ]
    assert read['starting_items'] == [stack(lore['rope'])]
    assert read['pregens'][0]['items'] == [stack(lore['potion'], 2)]


async def test_a_scenario_starts_without_items(client: AsyncClient, me: dict[str, str]):
    scenario = await create_scenario(client, me, None)

    assert (scenario['items'], scenario['starting_items']) == ([], [])


async def test_items_are_replaced_as_a_whole(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, items=[rule(lore['potion'])], starting_items=[stack(lore['rope'])])

    response = await client.patch(
        f'{SCENARIOS_URL}/{scenario["id"]}', json={'items': [rule(lore['rope'], 'gear')]}, headers=me
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert [item['entry_id'] for item in response.json()['items']] == [lore['rope']['id']]
    # 보내지 않은 칸은 그대로다
    assert response.json()['starting_items'] == [stack(lore['rope'])]


@pytest.mark.parametrize(
    'fields',
    [
        {'items': [{'entry_id': NO_SUCH_ID, 'kind': 'gear', 'effects': [{'kind': 'heal', 'magnitude': 'light'}]}]},
        {'items': [{'entry_id': NO_SUCH_ID, 'kind': 'weapon'}]},
        {
            'items': [
                {'entry_id': NO_SUCH_ID, 'kind': 'consumable', 'effects': [{'kind': 'heal', 'magnitude': 'Light!'}]}
            ]
        },
        {'items': [{'entry_id': NO_SUCH_ID, 'kind': 'gear'}, {'entry_id': NO_SUCH_ID, 'kind': 'consumable'}]},
        {'items': [{'entry_id': NO_SUCH_ID, 'kind': 'gear', 'extra': 1}]},
        {'starting_items': [{'entry_id': NO_SUCH_ID, 'count': 0}]},
        {'starting_items': [{'entry_id': NO_SUCH_ID, 'count': ITEM_STACK_MAX + 1}]},
        {'starting_items': [{'entry_id': NO_SUCH_ID, 'count': 1}, {'entry_id': NO_SUCH_ID, 'count': 2}]},
        {
            'starting_items': [
                {'entry_id': str(uuid.uuid4()), 'count': 1} for _ in range(SCENARIO_MAX_STARTING_ITEMS + 1)
            ]
        },
        {'pregens': [{'name': '기사', 'items': [{'entry_id': NO_SUCH_ID, 'count': 0}]}]},
    ],
    ids=[
        'heals-on-gear',
        'unknown-kind',
        'bad-magnitude-key',
        'same-item-twice',
        'extra-field',
        'zero-count',
        'too-many-of-one',
        'same-stack-twice',
        'too-many-stacks',
        'pregen-zero-count',
    ],
)
async def test_rejects_badly_shaped_items(client: AsyncClient, me: dict[str, str], fields: dict):
    response = await client.post(SCENARIOS_URL, json=with_model({'title': '추격전', **fields}), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 게시 ---


async def test_items_are_frozen_into_the_version(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(
        client,
        me,
        lore,
        items=[rule(lore['potion'], effects=[{'kind': 'heal', 'magnitude': 'light'}])],
        starting_items=[stack(lore['rope'], 3)],
        pregens=[pregen('기사', stack(lore['potion'], 2))],
    )

    snapshot = await published(client, me, scenario)

    assert snapshot['format'] == SNAPSHOT_FORMAT
    assert snapshot['items'] == [
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
            'treat_bonus': None,
        }
    ]
    assert snapshot['starting_items'] == [stack(lore['rope'], 3)]
    assert snapshot['pregens'][0]['items'] == [stack(lore['potion'], 2)]


@pytest.mark.parametrize(
    'where',
    ['items', 'starting_items', 'pregens'],
)
async def test_an_item_must_be_in_an_attached_lorebook(client: AsyncClient, me: dict[str, str], lore: dict, where):
    gone = {'id': NO_SUCH_ID}
    fields = {
        'items': {'items': [rule(gone, 'gear')]},
        'starting_items': {'starting_items': [stack(gone)]},
        'pregens': {'pregens': [pregen('기사', stack(gone))]},
    }[where]
    scenario = await scenario_with(client, me, lore, **fields)

    assert await refused(client, me, scenario) == ['item_entry_missing']


@pytest.mark.parametrize('where', ['items', 'starting_items', 'pregens'])
async def test_an_item_must_be_a_thing(client: AsyncClient, me: dict[str, str], lore: dict, where):
    fields = {
        'items': {'items': [rule(lore['lady'], 'gear')]},
        'starting_items': {'starting_items': [stack(lore['lady'])]},
        'pregens': {'pregens': [pregen('기사', stack(lore['lady']))]},
    }[where]
    scenario = await scenario_with(client, me, lore, **fields)

    assert await refused(client, me, scenario) == ['item_not_item']


async def test_an_item_in_a_detached_lorebook_is_missing(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, starting_items=[stack(lore['rope'])])

    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'lorebook_ids': []}, headers=me)

    # 로어북을 떼면 그 물건도 사라진다. 굳히기 전에 막는다
    assert await refused(client, me, scenario) == ['item_entry_missing']


async def test_healing_must_be_a_magnitude_of_the_rulebook(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(
        client, me, lore, items=[rule(lore['potion'], effects=[{'kind': 'heal', 'magnitude': 'enormous'}])]
    )

    assert await refused(client, me, scenario) == ['item_magnitude_missing']


async def test_a_consumable_may_heal_nothing(client: AsyncClient, me: dict[str, str], lore: dict):
    # 연막탄처럼 쓰면 없어지기만 하는 물건이다. 무엇이 일어나는지는 서술이 맡는다
    scenario = await scenario_with(client, me, lore, items=[rule(lore['potion'])])

    snapshot = await published(client, me, scenario)

    assert snapshot['items'] == [
        {
            'entry_id': lore['potion']['id'],
            'kind': 'consumable',
            'effects': [],
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
            'treat_bonus': None,
        }
    ]


# --- 판 ---


def entry(entry_id: uuid.UUID, kind: str) -> dict:
    return {'id': str(entry_id), 'name': '항목', 'keywords': [], 'content': '', 'kind': kind, 'true_names': []}


POTION = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000001')
ROPE = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000002')
LADY = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000003')
INN = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000004')


def snapshot_document(**fields) -> dict:
    """판 하나의 문서. 물건 둘과 인물 하나, 장소 하나가 든 로어북이 붙어 있다. 형식 17."""
    document = {
        'format': 17,
        'title': '판',
        'description': '',
        'rating': 'all',
        'openings': ['시작'],
        'recommended_players': {'min': 1, 'max': 4},
        'pregens': [],
        'character_modes': ['custom'],
        'default_sheet': SHEET,
        'npc_sheets': [],
        'default_npc_sheet': SHEET,
        'player_made_hp': None,
        'reroll_allowed': False,
        'narration_style': 'classic',
        'rulebook': read_snapshot_rulebook(),
        'world': None,
        'lorebooks': [
            {
                'id': str(uuid.uuid4()),
                'title': '로어북',
                'entries': [entry(POTION, 'item'), entry(LADY, 'person'), entry(INN, 'place'), entry(ROPE, 'item')],
            }
        ],
        'items': [],
        'starting_items': [],
    }
    document.update(fields)
    return document


def read_snapshot_rulebook() -> dict:
    """SRD5 템플릿을 규칙으로 둔 룰북."""
    return {'id': str(uuid.uuid4()), 'title': '룰북', 'gm_guide': '', 'rules': SRD5.model_dump(mode='json')}


def test_a_thing_without_a_rule_is_gear():
    snapshot = Snapshot.model_validate(
        snapshot_document(
            items=[{'entry_id': str(POTION), 'kind': 'consumable', 'effects': [{'kind': 'heal', 'magnitude': 'light'}]}]
        )
    )

    assert [entry.id for entry in item_entries(snapshot)] == [POTION, ROPE]
    potion, rope = item_rule_of(snapshot, POTION), item_rule_of(snapshot, ROPE)
    assert (potion.kind, [effect.model_dump(mode='json') for effect in potion.effects]) == (
        ItemKind.CONSUMABLE,
        [{'kind': 'heal', 'magnitude': 'light'}],
    )
    assert (rope.kind, rope.effects) == (ItemKind.GEAR, [])


@pytest.mark.parametrize(
    'fields',
    [
        {'items': [{'entry_id': str(LADY), 'kind': 'gear'}]},
        {'starting_items': [{'entry_id': str(INN), 'count': 1}]},
        {'starting_items': [{'entry_id': str(uuid.uuid4()), 'count': 1}]},
        {
            'pregens': [
                {'name': '기사', 'description': '', 'sheet': SHEET, 'items': [{'entry_id': str(LADY), 'count': 1}]}
            ]
        },
    ],
    ids=['rule-on-a-person', 'stack-of-a-place', 'unknown-stack', 'pregen-holds-a-person'],
)
def test_a_version_cannot_point_items_at_anything_but_things(fields: dict):
    # 게시가 막는 것을 판의 계약으로도 굳혀 둔다. 테이블은 소지품마다 물건 항목이 있다고 믿고 쓴다
    with pytest.raises(ValidationError):
        Snapshot.model_validate(snapshot_document(**fields))


def test_an_old_version_is_read_without_items():
    document = snapshot_document(format=16, pregens=[{'name': '기사', 'description': '', 'sheet': SHEET}])
    del document['items'], document['starting_items']

    upgraded = upgrade_from_16(document)
    snapshot = read_snapshot(document)

    assert (upgraded['format'], upgraded['items'], upgraded['starting_items']) == (17, [], [])
    assert upgraded['pregens'][0]['items'] == []
    # 받은 문서는 고치지 않는다
    assert 'items' not in document
    assert (snapshot.items, snapshot.starting_items, snapshot.pregens[0].items) == ([], [], [])
