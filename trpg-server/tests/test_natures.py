# trpg-server/tests/test_natures.py

"""
룰북이 정하는 성질과 타입마다의 면역(#886 ①)을 검증한다.

예전에는 다섯 성질(독, 기절, 감각, 몸, 정신)과 타입의 면역표(언데드는 독, 구조물은 독과 정신)가 엔진에 박혀 있었다.
이제 룰북의 규칙(natures, monster_immunities)이다. 템플릿과 옛 룰북과 옛 판은 그때의 값을 가진다. 하던 대로 돈다.

판은 test_monster_injuries.py 의 것이다. 수로 입구에 수로 쥐(야수)와 해골 병사(언데드). 룰북은 SRD5 에서 만든다.

넷을 본다.
  - 규칙: 성질의 이름표는 겹치지 않는다. 부상과 타입마다의 면역은 규칙의 성질만 가리킨다. 한 타입은 한 번만 적는다.
  - 룰북: 만들 때와 고칠 때 둘을 보낼 수 있다. 서로 가리키는 것이 맞지 않으면 422 이고, 먼저 틀린 칸을 알려 준다.
  - 시나리오와 판: 몬스터 시트의 면역과 약함은 규칙의 성질이어야 한다(monster_nature_invalid). 판의 면역은 룰북의 표다.
  - 옛 판(형식 66)과 옛 룰북(마이그레이션)은 그때 엔진의 값을 받고, 되돌리면 지운다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError

from app.assets.bestiaries.models import MonsterKind
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT
from app.assets.scenarios.upgrades import CLASSIC_MONSTER_IMMUNITIES, CLASSIC_NATURES, UPGRADES, upgrade_from_66
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.tables.monsters import immunities, kind_immunities
from tests import test_monster_injuries as injuries
from tests.test_npc_sheets import refused
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')

me = injuries.me
RULEBOOKS_URL = injuries.RULEBOOKS_URL
FIRE = {'key': 'fire', 'name': '화염', 'category': '원소'}
WITH_FIRE = [*CLASSIC_NATURES, FIRE]


async def patch(client: AsyncClient, url: str, headers: dict, **body):
    return await client.patch(url, json=body, headers=headers)


def rules_with(**fields) -> dict:
    return {**SRD5.model_dump(mode='json'), **fields}


# --- 규칙 ---


@pytest.mark.parametrize(
    ('fields', 'message'),
    [
        ({'natures': [*CLASSIC_NATURES, CLASSIC_NATURES[0]]}, '같은 성질'),
        ({'natures': CLASSIC_NATURES[1:]}, '부상의 성질이 규칙에 없습니다'),
        ({'monster_immunities': [{'kind': 'undead', 'natures': ['fire']}]}, '타입의 면역'),
        ({'monster_immunities': [*CLASSIC_MONSTER_IMMUNITIES, {'kind': 'undead', 'natures': []}]}, '같은 타입'),
        ({'monster_immunities': [{'kind': 'dragon', 'natures': []}]}, 'kind'),
        ({'monster_immunities': [{'kind': 'undead', 'natures': ['poison', 'poison']}]}, '같은 성질'),
    ],
    ids=['repeated', 'injury-points-nowhere', 'unknown-immunity', 'kind-twice', 'unknown-kind', 'repeated-in-kind'],
)
def test_the_rules_point_only_at_their_own_natures(fields: dict, message: str):
    with pytest.raises(ValidationError, match=message):
        Ruleset.model_validate(rules_with(**fields))


def test_a_nature_may_be_new_and_grouped():
    rules = Ruleset.model_validate(rules_with(natures=WITH_FIRE))

    assert (rules.natures[-1].key, rules.natures[-1].category) == ('fire', '원소')


@pytest.mark.parametrize(
    ('table', 'kind', 'expected'),
    [
        (CLASSIC_MONSTER_IMMUNITIES, MonsterKind.UNDEAD, {'poison'}),
        (CLASSIC_MONSTER_IMMUNITIES, MonsterKind.BEAST, set()),
        ([], MonsterKind.UNDEAD, set()),
        ([{'kind': 'beast', 'natures': ['fire']}], MonsterKind.BEAST, {'fire'}),
    ],
)
def test_the_kind_s_immunities_come_from_the_rulebook(table: list, kind: MonsterKind, expected: set):
    rules = Ruleset.model_validate(rules_with(natures=WITH_FIRE, monster_immunities=table))

    assert kind_immunities(rules, kind) == expected
    assert immunities(rules, injuries.snapshot_of(kind, ['stun'], [])) == expected | {'stun'}


# --- 룰북 ---


async def test_a_rulebook_takes_its_natures_from_the_template_or_the_request(client: AsyncClient, me: dict):
    plain = await injuries.post(client, RULEBOOKS_URL, me, title='그대로')
    own = await injuries.post(
        client,
        RULEBOOKS_URL,
        me,
        title='불',
        natures=WITH_FIRE,
        monster_immunities=[{'kind': 'beast', 'natures': ['fire']}],
    )

    assert (plain['rules']['natures'], plain['rules']['monster_immunities']) == (
        CLASSIC_NATURES,
        CLASSIC_MONSTER_IMMUNITIES,
    )
    assert (own['rules']['natures'][-1], own['rules']['monster_immunities']) == (
        FIRE,
        [{'kind': 'beast', 'natures': ['fire']}],
    )


async def test_the_natures_of_a_rulebook_can_be_changed(client: AsyncClient, me: dict):
    rulebook = await injuries.post(client, RULEBOOKS_URL, me, title='룰북')
    url = f'{RULEBOOKS_URL}/{rulebook["id"]}'
    without_mind = [nature for nature in CLASSIC_NATURES if nature['key'] != 'mind']
    no_mind_table = [{'kind': 'undead', 'natures': ['poison']}, {'kind': 'construct', 'natures': ['poison']}]

    # 구조물의 면역이 정신을 가리킨다. 성질만 지우면 틀리고, 둘을 함께 고치면 된다
    orphaned = await patch(client, url, me, natures=without_mind)
    unknown = await patch(client, url, me, monster_immunities=[{'kind': 'beast', 'natures': ['fire']}])
    both = await patch(client, url, me, natures=without_mind, monster_immunities=no_mind_table)
    # 부상이 쓰는 성질(독)은 지울 수 없다. 룰북의 부상은 고칠 수 없다
    poison_gone = await patch(client, url, me, natures=CLASSIC_NATURES[1:])
    # 둘을 보내 둘 다 틀리면 앞의 칸(성질)을 알려 준다
    first_wrong = await patch(client, url, me, natures=CLASSIC_NATURES[1:], monster_immunities=no_mind_table)

    assert (orphaned.status_code, orphaned.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'natures')
    assert (unknown.status_code, unknown.json()['field']) == (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        'monster_immunities',
    )
    assert both.status_code == status.HTTP_200_OK, both.text
    assert both.json()['rules']['monster_immunities'] == no_mind_table
    assert (poison_gone.status_code, poison_gone.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'natures')
    assert (first_wrong.status_code, first_wrong.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'natures')


# --- 시나리오와 판 ---


async def test_a_monster_sheet_points_at_the_rulebook_s_natures(client: AsyncClient, me: dict):
    unknown = await injuries.make_scenario(client, me, None, immune=['fire'])
    known = await injuries.make_scenario(client, me, {'natures': WITH_FIRE}, immune=['fire'])

    assert 'monster_nature_invalid' in await refused(client, me, unknown)
    published = await client.post(f'{injuries.SCENARIOS_URL}/{known["id"]}/versions', json={}, headers=me)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    assert published.json()['snapshot']['rulebook']['rules']['natures'][-1] == FIRE


async def test_a_rulebook_without_kind_immunities_lets_the_undead_be_poisoned(client: AsyncClient, me: dict):
    # 쥐(야수)는 몸의 성질에 면역이라 눈을 노릴 수 없다. 표를 비운 해골(언데드)은 노릴 수 있다
    table = await injuries.start_table(client, me, {'monster_immunities': [{'kind': 'beast', 'natures': ['body']}]})
    rat = await injuries.monster_named(client, me, table, '수로 쥐')
    skeleton = await injuries.monster_named(client, me, table, '해골 병사')

    at_rat = await injuries.send(client, me, table, injuries.BITE_BACK, injuries.strike(rat['id'], aim='lost_eye'))
    at_skeleton = await injuries.send(
        client, me, table, injuries.BITE_BACK, injuries.strike(skeleton['id'], aim='lost_eye')
    )

    assert (at_rat.status_code, at_rat.json()['reason']) == (status.HTTP_409_CONFLICT, 'target_immune')
    assert at_skeleton.status_code == status.HTTP_200_OK, at_skeleton.text


# --- 옛 판과 옛 룰북 ---


def test_an_old_version_gets_the_engine_s_old_values():
    old = {'format': 66, 'rulebook': {'rules': {'skills': []}}}

    upgraded = upgrade_from_66(old)

    assert upgraded['format'] == 67 == SNAPSHOT_FORMAT
    assert upgraded['rulebook']['rules'] == {
        'skills': [],
        'natures': CLASSIC_NATURES,
        'monster_immunities': CLASSIC_MONSTER_IMMUNITIES,
    }
    assert 'natures' not in old['rulebook']['rules']
    assert UPGRADES[66] is upgrade_from_66


def test_the_migration_fills_old_rulebooks_and_takes_new_natures_away_on_the_way_back():
    migration = load_migration('natures')

    filled = migration.with_natures({'injuries': []})
    back = migration.without_natures(filled)
    sheet = migration.classic_only({'monster_id': 'm', 'immune': ['fire', 'stun'], 'vulnerable': ['poison']})

    assert (filled['natures'], filled['monster_immunities']) == (CLASSIC_NATURES, CLASSIC_MONSTER_IMMUNITIES)
    assert migration.with_natures(filled) == filled
    assert back == {'injuries': []}
    assert sheet == {'monster_id': 'm', 'immune': ['stun'], 'vulnerable': ['poison']}
    # 마이그레이션은 앱의 코드를 가져오지 않는다. 그때의 값이 판을 올려 읽는 값과 같아야 한다
    assert (migration.CLASSIC_NATURES, migration.CLASSIC_MONSTER_IMMUNITIES) == (
        CLASSIC_NATURES,
        CLASSIC_MONSTER_IMMUNITIES,
    )
