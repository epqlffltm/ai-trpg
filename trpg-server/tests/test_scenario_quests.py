# trpg-server/tests/test_scenario_quests.py

"""
시나리오의 퀘스트 규칙을 검증한다.

셋을 본다.
  - 시나리오: 적고 읽고 고친다. 모양만 본다(시작 상태의 값, 같은 사건 두 줄 없음, 보상의 개수).
  - 게시: 붙인 로어북의 사건 항목을 가리키는지, 보상이 물건 항목인지.
  - 판: 형식 18 에 실린다. 옛 판은 퀘스트 규칙 없이 읽는다. 규칙이 없는 사건은 숨긴 채로 시작한다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.testing.tokens import SigningKey, make_access_claims, make_token

from app.assets.models import SCENARIO_MAX_QUEST_RULES, SCENARIO_MAX_STARTING_ITEMS, QuestStart
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, Snapshot, quest_entries, quest_rule_of, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_17
from app.main import API_PREFIX
from tests.narration_model import with_model
from tests.sheets import SHEET
from tests.test_npc_sheets import add_entry, create_scenario, post, published, refused
from tests.test_scenario_items import entry, snapshot_document, stack

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
    """사건 둘(광산의 비밀, 왕녀 구출), 물건 하나(치유 물약), 인물 하나가 든 로어북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='모험의 사건들')
    return {
        'lorebook': lorebook,
        'mine': await add_entry(client, me, lorebook, '광산의 비밀', 'event'),
        'rescue': await add_entry(client, me, lorebook, '왕녀 구출', 'event'),
        'potion': await add_entry(client, me, lorebook, '치유 물약', 'item'),
        'lady': await add_entry(client, me, lorebook, '악역영애', 'person'),
    }


def quest(entry: dict, **fields) -> dict:
    return {'entry_id': entry['id'], **fields}


async def scenario_with(client: AsyncClient, me: dict, lore: dict, **fields) -> dict:
    """사건 로어북을 붙이고, 인물에게 줄 기본 NPC 시트를 둔 시나리오."""
    return await create_scenario(client, me, lore, default_npc_sheet=SHEET, **fields)


# --- 시나리오: 적고 읽고 고친다 ---


async def test_quests_are_saved_and_read_back(client: AsyncClient, me: dict[str, str], lore: dict):
    quests = [quest(lore['rescue'], start='active', reward=[stack(lore['potion'], 2)]), quest(lore['mine'])]
    scenario = await scenario_with(client, me, lore, quests=quests)

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    # 시작 상태를 적지 않으면 숨김, 보상과 기한과 조건을 적지 않으면 없다
    assert read['quests'] == [
        {
            'entry_id': lore['rescue']['id'],
            'start': 'active',
            'reward': [stack(lore['potion'], 2)],
            'reward_money': 0,
            'time_limit_minutes': None,
            'conditions': [],
            'match': 'all',
            'reveal': [],
            'reveal_match': 'all',
            'fail': [],
            'fail_match': 'all',
        },
        {
            'entry_id': lore['mine']['id'],
            'start': 'hidden',
            'reward': [],
            'reward_money': 0,
            'time_limit_minutes': None,
            'conditions': [],
            'match': 'all',
            'reveal': [],
            'reveal_match': 'all',
            'fail': [],
            'fail_match': 'all',
        },
    ]


async def test_a_scenario_starts_without_quests(client: AsyncClient, me: dict[str, str]):
    scenario = await create_scenario(client, me, None)

    assert scenario['quests'] == []


async def test_quests_are_replaced_as_a_whole(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(
        client, me, lore, quests=[quest(lore['mine'])], starting_items=[stack(lore['potion'])]
    )

    response = await client.patch(
        f'{SCENARIOS_URL}/{scenario["id"]}', json={'quests': [quest(lore['rescue'], start='active')]}, headers=me
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert [rule['entry_id'] for rule in response.json()['quests']] == [lore['rescue']['id']]
    # 보내지 않은 칸은 그대로다
    assert response.json()['starting_items'] == [stack(lore['potion'])]


@pytest.mark.parametrize(
    'quests',
    [
        [{'entry_id': NO_SUCH_ID, 'start': 'done'}],
        [{'entry_id': NO_SUCH_ID}, {'entry_id': NO_SUCH_ID, 'start': 'active'}],
        [{'entry_id': NO_SUCH_ID, 'extra': 1}],
        [{'entry_id': NO_SUCH_ID, 'reward': [{'entry_id': NO_SUCH_ID, 'count': 0}]}],
        [{'entry_id': NO_SUCH_ID, 'reward': [{'entry_id': NO_SUCH_ID, 'count': 1}] * 2}],
        [
            {
                'entry_id': NO_SUCH_ID,
                'reward': [{'entry_id': str(uuid.uuid4()), 'count': 1} for _ in range(SCENARIO_MAX_STARTING_ITEMS + 1)],
            }
        ],
        [{'entry_id': str(uuid.uuid4())} for _ in range(SCENARIO_MAX_QUEST_RULES + 1)],
    ],
    ids=[
        'unknown-start',
        'same-event-twice',
        'extra-field',
        'zero-reward',
        'same-reward-twice',
        'too-many-rewards',
        'too-many-quests',
    ],
)
async def test_rejects_badly_shaped_quests(client: AsyncClient, me: dict[str, str], quests: list):
    response = await client.post(SCENARIOS_URL, json=with_model({'title': '추격전', 'quests': quests}), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_accepts_the_most_quests_allowed(client: AsyncClient, me: dict[str, str]):
    quests = [{'entry_id': str(uuid.uuid4())} for _ in range(SCENARIO_MAX_QUEST_RULES)]

    scenario = await create_scenario(client, me, None, quests=quests)

    assert len(scenario['quests']) == SCENARIO_MAX_QUEST_RULES


# --- 게시 ---


async def test_quests_are_frozen_into_the_version(client: AsyncClient, me: dict[str, str], lore: dict):
    quests = [quest(lore['rescue'], start='active', reward=[stack(lore['potion'], 2)])]
    scenario = await scenario_with(client, me, lore, quests=quests)

    snapshot = await published(client, me, scenario)

    assert snapshot['format'] == SNAPSHOT_FORMAT
    assert snapshot['quests'] == [
        {
            'entry_id': lore['rescue']['id'],
            'start': 'active',
            'reward': [stack(lore['potion'], 2)],
            'reward_money': 0,
            'time_limit_minutes': None,
            'conditions': [],
            'match': 'all',
            'reveal': [],
            'reveal_match': 'all',
            'fail': [],
            'fail_match': 'all',
        }
    ]


async def test_a_quest_must_be_in_an_attached_lorebook(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, quests=[quest({'id': NO_SUCH_ID})])

    assert await refused(client, me, scenario) == ['quest_entry_missing']


@pytest.mark.parametrize('kind', ['potion', 'lady'])
async def test_a_quest_must_be_an_event(client: AsyncClient, me: dict[str, str], lore: dict, kind: str):
    scenario = await scenario_with(client, me, lore, quests=[quest(lore[kind])])

    assert await refused(client, me, scenario) == ['quest_not_event']


async def test_a_quest_in_a_detached_lorebook_is_missing(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, quests=[quest(lore['mine'])])

    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'lorebook_ids': []}, headers=me)

    # 로어북을 떼면 그 사건도 사라진다. 굳히기 전에 막는다
    assert await refused(client, me, scenario) == ['quest_entry_missing']


async def test_a_reward_must_be_in_an_attached_lorebook(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, quests=[quest(lore['mine'], reward=[stack({'id': NO_SUCH_ID})])])

    # 보상은 소지품이 된다. 아이템과 같은 문제로 막는다
    assert await refused(client, me, scenario) == ['item_entry_missing']


async def test_a_reward_must_be_a_thing(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, quests=[quest(lore['mine'], reward=[stack(lore['rescue'])])])

    assert await refused(client, me, scenario) == ['item_not_item']


# --- 판 ---


MINE = uuid.UUID('bbbbbbbb-0000-4000-8000-000000000001')
RESCUE = uuid.UUID('bbbbbbbb-0000-4000-8000-000000000002')
POTION = uuid.UUID('bbbbbbbb-0000-4000-8000-000000000003')
INN = uuid.UUID('bbbbbbbb-0000-4000-8000-000000000004')


def quest_document(**fields) -> dict:
    """판 하나의 문서. 사건 둘, 물건 하나, 장소 하나가 든 로어북이 붙어 있다. 형식 18."""
    lorebook = {
        'id': str(uuid.uuid4()),
        'title': '로어북',
        'entries': [entry(MINE, 'event'), entry(POTION, 'item'), entry(INN, 'place'), entry(RESCUE, 'event')],
    }
    return snapshot_document(**{'format': 18, 'lorebooks': [lorebook], 'quests': [], **fields})


def test_an_event_without_a_rule_starts_hidden():
    rule = {'entry_id': str(RESCUE), 'start': 'active', 'reward': [{'entry_id': str(POTION), 'count': 2}]}
    snapshot = Snapshot.model_validate(quest_document(quests=[rule]))

    assert [entry.id for entry in quest_entries(snapshot)] == [MINE, RESCUE]
    rescue = quest_rule_of(snapshot, RESCUE)
    assert (rescue.start, [(stack.entry_id, stack.count) for stack in rescue.reward]) == (
        QuestStart.ACTIVE,
        [(POTION, 2)],
    )
    assert (quest_rule_of(snapshot, MINE).start, quest_rule_of(snapshot, MINE).reward) == (QuestStart.HIDDEN, [])


@pytest.mark.parametrize(
    'rule',
    [
        {'entry_id': str(POTION)},
        {'entry_id': str(INN)},
        {'entry_id': str(uuid.uuid4())},
        {'entry_id': str(MINE), 'reward': [{'entry_id': str(RESCUE), 'count': 1}]},
        {'entry_id': str(MINE), 'reward': [{'entry_id': str(uuid.uuid4()), 'count': 1}]},
    ],
    ids=['quest-on-a-thing', 'quest-on-a-place', 'unknown-quest', 'reward-of-an-event', 'unknown-reward'],
)
def test_a_version_cannot_point_quests_at_anything_but_events(rule: dict):
    # 게시가 막는 것을 판의 계약으로도 굳혀 둔다. 테이블은 퀘스트마다 사건, 보상마다 물건이 있다고 믿고 쓴다
    with pytest.raises(ValidationError):
        Snapshot.model_validate(quest_document(quests=[rule]))


def test_an_old_version_is_read_without_quest_rules():
    document = quest_document(format=17)
    del document['quests']

    upgraded = upgrade_from_17(document)
    snapshot = read_snapshot(document)

    assert (upgraded['format'], upgraded['quests']) == (18, [])
    # 받은 문서는 고치지 않는다
    assert 'quests' not in document
    # 사건은 그대로 퀘스트다. 모두 숨긴 채로 시작한다
    assert snapshot.quests == []
    assert [quest_rule_of(snapshot, entry.id).start for entry in quest_entries(snapshot)] == [QuestStart.HIDDEN] * 2
