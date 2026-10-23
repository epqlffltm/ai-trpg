# trpg-server/tests/test_npc_attack_sheets.py

"""
NPC 시트의 공격(#487 1/2)을 검증한다. 공격을 쓰는 차례는 2/2 에서 붙는다.

판은 test_npc_sheets.py 의 것이다(악역영애, 드워프). 공격은 test_monster_rules.py 의 것을 그대로 쓴다.

보는 것.
  - 시나리오: NPC 시트에 공격을 적고 읽는다. 모양은 몬스터 시트의 공격과 같다(이름, 능력치, 난이도, 피해의 등급).
    적지 않으면 공격이 없다. 같은 이름이 둘이거나 너무 많으면 거부한다.
  - 게시: 이름표가 룰북에 없으면 npc_attack_invalid 다. 몬스터의 것(monster_attack_invalid)과 따로 알린다.
  - 판 형식 41: 판의 NPC 시트에 공격이 실린다. 옛 판의 인물은 공격이 없는 것으로 읽는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token

from app.assets.scenarios.schemas import MONSTER_MAX_ATTACKS
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_40
from app.main import API_PREFIX
from tests.narration_model import with_model
from tests.sheets import SHEET
from tests.test_monster_rules import BITE, SLAM
from tests.test_npc_sheets import (
    LADY_SHEET,
    LOREBOOKS_URL,
    ME,
    NPC_DEFAULT,
    add_entry,
    create_scenario,
    npc,
    post,
    published,
    refused,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만드는 사람이다."""
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """인물 하나(악역영애)가 든 로어북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='추격전의 인물들')
    return {'lorebook': lorebook, 'lady': await add_entry(client, me, lorebook, '악역영애', 'person')}


def armed(lore: dict, attacks: list[dict]) -> dict:
    """공격을 적은 악역영애의 시트."""
    return {**npc(lore['lady'], LADY_SHEET), 'attacks': attacks}


async def with_attacks(client: AsyncClient, me: dict[str, str], lore: dict, attacks: list[dict]) -> dict:
    """악역영애에게 공격을 적은 시나리오."""
    return await create_scenario(client, me, lore, npc_sheets=[armed(lore, attacks)], default_npc_sheet=NPC_DEFAULT)


# --- 시나리오 ---


async def test_attacks_are_saved_and_read_back(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await with_attacks(client, me, lore, [BITE, SLAM])

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    assert read['npc_sheets'][0]['attacks'] == [BITE, SLAM]


async def test_a_sheet_without_attacks_has_none(client: AsyncClient, me: dict[str, str], lore: dict):
    sheet = {'entry_id': lore['lady']['id'], 'sheet': LADY_SHEET}
    scenario = await create_scenario(client, me, lore, npc_sheets=[sheet], default_npc_sheet=NPC_DEFAULT)

    assert scenario['npc_sheets'][0]['attacks'] == []


@pytest.mark.parametrize(
    'attacks',
    [
        [{**BITE, 'harm': None}],
        [{**BITE, 'name': '   '}],
        [{**BITE, 'damage': 3}],
        [BITE, {**SLAM, 'name': BITE['name']}],
        [{**BITE, 'name': f'공격{number}'} for number in range(MONSTER_MAX_ATTACKS + 1)],
    ],
)
async def test_attacks_must_have_the_shape_of_a_monster_attack(
    client: AsyncClient, me: dict[str, str], lore: dict, attacks: list[dict]
):
    response = await client.post(
        SCENARIOS_URL,
        json=with_model({'title': '추격전', 'npc_sheets': [armed(lore, attacks)]}),
        headers=me,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 게시 ---


async def test_the_snapshot_carries_the_attacks(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await with_attacks(client, me, lore, [BITE])

    snapshot = await published(client, me, scenario)

    assert snapshot['format'] == SNAPSHOT_FORMAT >= 41
    assert snapshot['npc_sheets'] == [armed(lore, [BITE])]


@pytest.mark.parametrize(
    'attack',
    [{**BITE, 'ability': 'luck'}, {**BITE, 'difficulty': 'impossible'}, {**BITE, 'harm': 'apocalyptic'}],
)
async def test_an_attack_outside_the_rules_is_refused(
    client: AsyncClient, me: dict[str, str], lore: dict, attack: dict
):
    scenario = await with_attacks(client, me, lore, [SLAM, attack])

    assert await refused(client, me, scenario) == ['npc_attack_invalid']


# --- 옛 판 ---


def test_an_old_snapshot_reads_everyone_as_unarmed():
    sheet = {'entry_id': str(uuid.uuid4()), 'sheet': SHEET, 'on_caught': 'fight'}
    document = {'format': 40, 'npc_sheets': [sheet]}

    upgraded = upgrade_from_40(document)

    assert upgraded['format'] == 41
    assert upgraded['npc_sheets'] == [{**sheet, 'attacks': []}]
    assert 'attacks' not in document['npc_sheets'][0]
    assert UPGRADES[40] is upgrade_from_40


def test_an_old_snapshot_without_npc_sheets_stays_without():
    assert upgrade_from_40({'format': 40})['npc_sheets'] == []
