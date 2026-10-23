# trpg-server/tests/test_references_sheets.py

"""
SRD 몬스터의 수치로 몬스터 시트를 제안하는 것(#482 4단계)을 검증한다.

보는 것.
  - 옮기는 규칙(app/references/sheets.py): 점수와 HP 를 범위에 맞추고, 명중 보너스가 있는 행동만 공격으로 옮긴다.
    공격의 능력치(근력과 민첩 중), 난이도(맞힐 확률을 맞춘 것), 피해의 등급(평균이 가까운 것), 이름(흔한 것은 한국어).
    바꾼 것은 notes 로 알린다. SRD 의 능력치가 없는 규칙은 거부한다.
  - 제안 API: 저장하지 않는다. 시나리오의 monster_sheets 에 그대로 넣을 수 있다.
    남의 시나리오, 붙이지 않은 도감의 몬스터, 룰북이 없는 시나리오, 복사하지 않은 몬스터를 가린다.
  - 저장소의 SRD 몬스터 모두에 srd5 시트를 제안할 수 있다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import MONSTER_MAX_ATTACKS
from app.assets.scenarios.schemas import MonsterSheet
from app.engine.ruleset import Ability
from app.engine.sheet import SHEET_MAX_HP
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.references.loading import load_document
from app.references.records import ReferenceKind, ReferenceRecord, read_document
from app.references.sheets import (
    RulesNotSrdError,
    attack_name,
    damage_average,
    dice_average,
    nearest_difficulty,
    nearest_magnitude,
    proficiency_of,
    propose,
)
from tests.narration_model import with_model
from tests.test_references_copy import document
from tests.test_srd_references import DATA_FILE

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')

ABILITIES = {'strength': 12, 'dexterity': 15, 'constitution': 12, 'intelligence': 3, 'wisdom': 12, 'charisma': 6}
# 늑대. 명중 +4(숙련 2 + 민첩 2), 물기 2d4+2(평균 7)
WOLF_DATA = {
    'abilities': ABILITIES,
    'hit_points': 11,
    'challenge_rating': 0.25,
    'actions': [{'name': 'Bite', 'attack_bonus': 4, 'damage': [{'dice': '2d4+2', 'type': 'piercing'}]}],
}
# 늙은 붉은 용. 점수와 HP 가 이 엔진의 범위를 넘는다. 숨결은 내성으로 막는다
DRAGON_DATA = {
    'abilities': {**ABILITIES, 'strength': 30, 'constitution': 29, 'charisma': 27},
    'hit_points': 1200,
    'challenge_rating': 24,
    'actions': [
        {'name': 'Multiattack'},
        {'name': 'Bite', 'attack_bonus': 17, 'damage': [{'dice': '2d10+10', 'type': 'piercing'}]},
        {'name': 'Fire Breath', 'dc': {'ability': 'dex', 'value': 24}},
    ],
}
WOLF = ReferenceRecord(key='monsters/wolf', kind=ReferenceKind.MONSTER, name='Wolf', data=WOLF_DATA, name_ko='늑대')


# --- 옮기는 규칙 ---


def test_a_wolf_keeps_its_numbers_and_gets_one_attack():
    proposal = propose(SRD5, WOLF_DATA)

    assert proposal.sheet.abilities == {'str': 12, 'dex': 15, 'con': 12, 'int': 3, 'wis': 12, 'cha': 6}
    assert proposal.sheet.max_hp == 11
    (bite,) = proposal.attacks
    # 민첩(+2)과 숙련(+2)이 명중 +4 를 설명한다. 13 - 4 + 2 = 11 에 가까운 쉬움(10). 평균 7 은 심함(2d8, 9)에 가깝다
    assert (bite.name, bite.ability, bite.difficulty, bite.harm) == ('물기', 'dex', 'easy', 'heavy')
    assert proposal.notes == []


def test_numbers_beyond_the_rules_are_fitted_and_told():
    proposal = propose(SRD5, DRAGON_DATA)

    assert proposal.sheet.abilities['str'] == 20 and proposal.sheet.abilities['cha'] == 20
    assert proposal.sheet.max_hp == SHEET_MAX_HP
    assert [attack.name for attack in proposal.attacks] == ['물기']
    assert proposal.notes == [
        '근력 30 을(를) 규칙의 범위에 맞춰 20 로 바꿨다.',
        '건강 29 을(를) 규칙의 범위에 맞춰 20 로 바꿨다.',
        '매력 27 을(를) 규칙의 범위에 맞춰 20 로 바꿨다.',
        f'HP 1200 을(를) 시트의 상한에 맞춰 {SHEET_MAX_HP} 로 바꿨다.',
        '명중으로 맞히지 않는 행동은 옮기지 않았다: Fire Breath.',
    ]
    # 범위에 맞춘 근력(+5)으로 맞힌다. 13 - 17 + 5 = 1 에 가까운 매우 쉬움(5)
    assert proposal.attacks[0].difficulty == 'very_easy'


def test_attacks_without_damage_get_the_middle_harm_and_repeats_and_extras_are_dropped():
    actions = [
        {'name': 'Web', 'attack_bonus': 4},
        {'name': 'Claw', 'attack_bonus': 4, 'damage': [{'dice': '1', 'type': 'slashing'}]},
        {'name': 'Claws', 'attack_bonus': 4, 'damage': [{'dice': '1d4', 'type': 'slashing'}]},
        *[{'name': f'Strike {number}', 'attack_bonus': 4, 'damage': [{'dice': '1d6'}]} for number in range(5)],
    ]

    proposal = propose(SRD5, {**WOLF_DATA, 'actions': actions})

    assert [attack.name for attack in proposal.attacks] == ['거미줄', '발톱', 'Strike 0', 'Strike 1', 'Strike 2']
    assert len(proposal.attacks) == MONSTER_MAX_ATTACKS
    assert (proposal.attacks[0].harm, proposal.attacks[1].harm) == ('moderate', 'light')
    assert proposal.notes == [
        '거미줄: 피해를 알 수 없어 보통 등급으로 두었다.',
        f'공격이 {MONSTER_MAX_ATTACKS}개를 넘어 앞의 {MONSTER_MAX_ATTACKS}개만 옮겼다.',
    ]


def test_the_attack_ability_is_strength_or_dexterity_that_explains_the_bonus():
    strong = {**ABILITIES, 'strength': 18, 'dexterity': 10}
    action = {'name': 'Greataxe', 'attack_bonus': 6, 'damage': [{'dice': '1d12+4'}]}

    (axe,) = propose(SRD5, {**WOLF_DATA, 'abilities': strong, 'actions': [action]}).attacks
    # 지혜로 설명되는 보너스여도 근력과 민첩 중에서 고른다. 같으면 근력이다
    (touch,) = propose(SRD5, {**WOLF_DATA, 'abilities': {**ABILITIES, 'dexterity': 12}, 'actions': [action]}).attacks

    assert axe.ability == 'str'
    assert touch.ability == 'str'


@pytest.mark.parametrize(
    ('dice', 'average'), [('2d6+5', 12.0), ('1d12', 6.5), ('1', 1.0), ('1d4 - 1', 1.5), ('?', None)]
)
def test_the_average_of_the_dice(dice: str, average: float | None):
    assert dice_average(dice) == average


@pytest.mark.parametrize(('challenge', 'bonus'), [(0, 2), (0.25, 2), (4, 2), (5, 3), (9, 4), (17, 6), (30, 9)])
def test_the_proficiency_follows_the_challenge(challenge: float, bonus: int):
    assert proficiency_of(challenge) == bonus


def test_the_nearest_difficulty_and_harm():
    assert nearest_difficulty(SRD5, 12).key == 'easy'
    assert nearest_difficulty(SRD5, 7).key == 'very_easy' and nearest_difficulty(SRD5, 13).key == 'medium'
    # 평균이 두 등급의 한가운데면 약한 쪽이다(3.5, 6.75)
    assert [nearest_magnitude(SRD5, value).key for value in (1, 3.5, 6.75, 7, 30)] == [
        'light',
        'light',
        'moderate',
        'heavy',
        'heavy',
    ]


def test_an_unknown_attack_keeps_its_name_within_the_limit():
    assert attack_name('Bite') == '물기'
    assert attack_name('Very Long Attack Name That Goes On And On') == 'Very Long Attack Name That Goe'


def test_rules_without_the_srd_abilities_are_refused():
    rules = SRD5.model_copy(update={'abilities': (Ability(key='body', name='몸'), *SRD5.abilities[1:])})

    with pytest.raises(RulesNotSrdError) as caught:
        propose(rules, WOLF_DATA)

    assert caught.value.missing == ['str']


def test_every_srd_monster_gets_a_sheet_that_the_scenario_takes():
    monsters = [entry for entry in read_document(DATA_FILE).entries if entry.kind == ReferenceKind.MONSTER]

    for monster in monsters:
        proposal = propose(SRD5, monster.data)
        try:
            MonsterSheet(monster_id=uuid.uuid4(), sheet=proposal.sheet, attacks=proposal.attacks)
        except ValidationError as error:  # pragma: no cover - 실패할 때 어느 몬스터인지 보인다
            pytest.fail(f'{monster.key}: {error}')
        assert {attack.difficulty for attack in proposal.attacks} <= {d.key for d in SRD5.difficulties}


# --- 제안 API ---


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def my_headers(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def their_headers(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


async def post(client: AsyncClient, headers: dict, path: str, body: dict) -> dict:
    response = await client.post(f'{API_PREFIX}{path}', json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


@pytest.fixture
async def wolf_id(clean_tables: None, session: AsyncSession) -> str:
    """테이블을 비우고 늑대를 참고 자료로 넣는다. 그 id."""
    await load_document(session, document(WOLF))
    return str(await session.scalar(text("SELECT id FROM reference_entries WHERE key = 'monsters/wolf'")))


async def set_up(client: AsyncClient, headers: dict, wolf_id: str, rulebook: bool = True, attach: bool = True):
    """도감에 늑대를 복사하고 직접 쓴 몬스터도 하나 두고, 룰북과 도감을 붙인 시나리오를 만든다."""
    bestiary = await post(client, headers, '/bestiaries', {'title': '짐승'})
    copied = await post(client, headers, f'/bestiaries/{bestiary["id"]}/monsters/copies', {'reference_ids': [wolf_id]})
    written = await post(client, headers, f'/bestiaries/{bestiary["id"]}/monsters', {'name': '수로 쥐'})
    body: dict = {'title': '숲'}
    if rulebook:
        body['rulebook_id'] = (await post(client, headers, '/rulebooks', {'title': 'srd5'}))['id']
    if attach:
        body['bestiary_ids'] = [bestiary['id']]
    scenario = await post(client, headers, '/scenarios', with_model(body))
    return scenario, copied['created'][0], written


def proposal_url(scenario: dict, monster: dict) -> str:
    return f'{API_PREFIX}/scenarios/{scenario["id"]}/monsters/{monster["id"]}/sheet-proposal'


async def test_a_sheet_is_proposed_for_a_copied_monster_and_not_saved(
    client: AsyncClient, my_headers: dict, wolf_id: str
):
    scenario, wolf, _ = await set_up(client, my_headers, wolf_id)

    response = await client.get(proposal_url(scenario, wolf), headers=my_headers)
    saved = await client.get(f'{API_PREFIX}/scenarios/{scenario["id"]}', headers=my_headers)

    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body['sheet']['monster_id'] == wolf['id']
    assert body['sheet']['sheet'] == {'abilities': propose(SRD5, WOLF_DATA).sheet.abilities, 'max_hp': 11}
    attack = {'name': '물기', 'ability': 'dex', 'difficulty': 'easy', 'harm': 'heavy', 'weapon': None}
    assert body['sheet']['attacks'] == [attack]
    assert body['notes'] == [] and body['copied_from'] == {'source': 'srd51', 'key': 'monsters/wolf'}
    assert saved.json()['monster_sheets'] == []


async def test_the_proposal_can_be_saved_as_it_is(client: AsyncClient, my_headers: dict, wolf_id: str):
    scenario, wolf, _ = await set_up(client, my_headers, wolf_id)
    proposed = (await client.get(proposal_url(scenario, wolf), headers=my_headers)).json()

    response = await client.patch(
        f'{API_PREFIX}/scenarios/{scenario["id"]}', json={'monster_sheets': [proposed['sheet']]}, headers=my_headers
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['monster_sheets'] == [proposed['sheet']]


async def test_someone_elses_scenario_looks_like_it_does_not_exist(
    client: AsyncClient, my_headers: dict, their_headers: dict, wolf_id: str
):
    scenario, wolf, _ = await set_up(client, their_headers, wolf_id)

    response = await client.get(proposal_url(scenario, wolf), headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_a_monster_of_a_bestiary_not_attached_is_not_found(client: AsyncClient, my_headers: dict, wolf_id: str):
    scenario, wolf, _ = await set_up(client, my_headers, wolf_id, attach=False)

    response = await client.get(proposal_url(scenario, wolf), headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_a_scenario_without_a_rulebook_cannot_be_proposed_for(
    client: AsyncClient, my_headers: dict, wolf_id: str
):
    scenario, wolf, _ = await set_up(client, my_headers, wolf_id, rulebook=False)

    response = await client.get(proposal_url(scenario, wolf), headers=my_headers)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['code'] == 'no_rulebook'


async def test_a_written_monster_or_a_vanished_reference_has_nothing_to_propose(
    client: AsyncClient, my_headers: dict, wolf_id: str, session: AsyncSession
):
    scenario, wolf, written = await set_up(client, my_headers, wolf_id)

    mine = await client.get(proposal_url(scenario, written), headers=my_headers)
    await load_document(session, document())
    vanished = await client.get(proposal_url(scenario, wolf), headers=my_headers)

    assert (mine.status_code, mine.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'not_copied')
    assert (vanished.status_code, vanished.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'not_copied')


def test_the_difficulty_uses_the_fitted_score_the_sheet_rolls_with():
    # 근력 30(보정 +10)이 20(+5)이 된다. 판정은 시트의 점수로 하니 13 - 11 + 5 = 7, 매우 쉬움이다(원본이면 12, 쉬움)
    action = {'name': 'Slam', 'attack_bonus': 11, 'damage': [{'dice': '2d8'}]}

    (slam,) = propose(SRD5, {**WOLF_DATA, 'abilities': {**ABILITIES, 'strength': 30}, 'actions': [action]}).attacks

    assert (slam.ability, slam.difficulty) == ('str', 'very_easy')


def test_the_damage_of_several_kinds_is_added():
    action = {'damage': [{'dice': '2d6+5'}, {'dice': '1d12'}, {'dice': '?'}]}

    assert damage_average(action) == 18.5
    assert damage_average({'damage': [{'dice': '?'}]}) is None
