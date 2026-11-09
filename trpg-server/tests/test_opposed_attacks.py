# trpg-server/tests/test_opposed_attacks.py

"""
맞서는 굴림(#254)을 검증한다. 공격을 받는 쪽도 굴려, 공격하는 쪽의 합이 더 높아야 맞는다(같으면 막는다).

  - 엔진(app/engine/check.py 의 resolve_opposed): over 와 under, 같으면 막음, 불리함, 난이도의 보정(difficulty_shift)
  - 막는 능력치(app/rounds/defenses.py): 공격에 적은 것, 없으면 규칙의 것, 규칙에 없으면 고정 난이도
  - 규칙: 막는 능력치는 규칙의 능력치여야 한다. 템플릿마다 있다
  - 옛 판(upgrade_from_69)은 막는 규칙이 없는 것으로 읽는다. 마이그레이션은 룰북에 한 번만 채우고 되돌린다
  - 룰북 API: 막는 규칙을 고친다. 없는 능력치면 422 다
  - 몬스터의 차례: 받는 캐릭터가 굴리고(차례의 outcome 의 defense), 공격의 막는 능력치를 따르고, 같으면 막는다.
    몬스터가 치는 인물도 굴린다
  - 싸우는 NPC 의 차례: 받는 캐릭터가 굴린다
판은 다른 테스트 파일의 것을 빌린다(수로 쥐, 약사, 악역영애). 이 파일의 테스트는 막는 규칙을 빼지 않은 룰북을 쓴다
(@pytest.mark.opposed, tests/conftest.py).
"""

import importlib.util
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import AttackSnapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_69
from app.engine.check import Side, difficulty_shift, find_difficulty, resolve_opposed
from app.engine.dice import ScriptedDice
from app.engine.injury import Hindrance
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5, TEMPLATES
from app.main import API_PREFIX
from app.rounds import defenses
from app.rounds.blows import NO_BLOW
from tests import test_check_styles as styles
from tests import test_monster_npc_attacks as bystanders
from tests import test_monster_turns as turns
from tests import test_npc_turns as npc_fights
from tests.narration_model import asset_body

pytestmark = [pytest.mark.usefixtures('clean_tables'), pytest.mark.opposed]

TEMPLATE = SRD5.model_dump(mode='json')
LIMPING = Hindrance(penalty=2, disadvantage=False, injuries=())


def side(score: int = 10, adjust: int = 0, **others) -> Side:
    return Side(score=score, adjust=adjust, **others)


def attack(**changes) -> AttackSnapshot:
    return AttackSnapshot(**{'name': '물기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light', **changes})


# --- 엔진 ---


def test_the_higher_total_hits_and_a_tie_holds():
    hit = resolve_opposed(SRD5, side(), side(), ScriptedDice([12, 11]))
    tie = resolve_opposed(SRD5, side(), side(), ScriptedDice([12, 12]))

    assert (hit.attack.check.success, hit.attack.check.target, hit.defense.check.success) == (True, 12, False)
    assert (tie.attack.check.success, tie.defense.check.success, tie.defense.check.target) == (False, True, 12)


def test_scores_weapons_and_wounds_count_on_both_sides():
    # 공격: 점수 14(보정 +2)와 무기 +1. 받는 쪽: 점수 12(보정 +1), 방어구 +3, 다쳐서 -2
    rolled = resolve_opposed(SRD5, side(14, 1), side(12, 3, hindrance=LIMPING), ScriptedDice([10, 10]))

    assert (rolled.attack.check.total, rolled.defense.check.total) == (13, 12)
    assert rolled.attack.check.success is True
    assert rolled.defense.hindrance is LIMPING


def test_disadvantage_rolls_twice_and_keeps_the_worse():
    rolled = resolve_opposed(SRD5, side(disadvantage=True), side(), ScriptedDice([18, 4, 9]))

    assert (rolled.attack.rolls, rolled.attack.check.roll, rolled.attack.check.success) == ((18, 4), 4, False)


def test_under_compares_the_margins():
    rules = styles.D100
    # 기량 50: 공격은 20 을 굴려 여유 30, 받는 쪽은 35 를 굴려 여유 15. 공격의 여유가 크다
    wins = resolve_opposed(rules, side(50), side(50), ScriptedDice([20, 35]))
    # 공격의 여유 10, 받는 쪽의 여유 10. 같으면 막는다
    ties = resolve_opposed(rules, side(50), side(50), ScriptedDice([40, 40]))
    # 받는 쪽이 제 기량 밖이면(60 > 50) 공격이 기량 안이기만 하면 맞는다
    slips = resolve_opposed(rules, side(50), side(50), ScriptedDice([49, 60]))
    # 공격이 제 기량 밖이면 늘 빗나간다
    fumbles = resolve_opposed(rules, side(50), side(50), ScriptedDice([70, 90]))

    assert [one.attack.check.success for one in (wins, ties, slips, fumbles)] == [True, False, True, False]
    assert (slips.defense.check.success, slips.defense.check.target) == (False, 50)


def test_the_difficulty_becomes_a_bonus_from_the_default():
    easy, medium, hard = (find_difficulty(SRD5, key) for key in ('easy', 'medium', 'hard'))

    assert [difficulty_shift(SRD5, one) for one in (easy, medium, hard)] == [5, 0, -5]
    assert difficulty_shift(styles.D100, hard) == -20


# --- 막는 능력치 ---


def test_the_attack_picks_its_own_defense_or_the_rules_one():
    fixed = Ruleset.model_validate({**TEMPLATE, 'defense': None})

    assert defenses.defending_ability(SRD5, attack()) == 'dex'
    assert defenses.defending_ability(SRD5, attack(defense='con')) == 'con'
    assert defenses.defending_ability(fixed, attack(defense='con')) is None


def test_the_attacker_side_carries_the_weapon_the_difficulty_and_the_wounds():
    sided = defenses.attacker_side(SRD5, {'str': 14}, [], attack(difficulty='hard'), NO_BLOW)

    assert (sided.score, sided.adjust) == (14, -5)


def test_the_member_defends_with_armor_raising_the_bar():
    member = SimpleNamespace(sheet=SimpleNamespace(abilities={'dex': 16, 'con': 8}, injuries=[]))
    blow = replace(NO_BLOW, raise_by=2)

    sided = defenses.member_defense(SRD5, member, attack(defense='con'), blow)

    assert (sided.score, sided.adjust) == (8, 2)


# --- 규칙 ---


def test_the_defense_must_be_one_of_the_abilities():
    with pytest.raises(ValidationError, match='막는 능력치'):
        Ruleset.model_validate({**TEMPLATE, 'defense': {'ability': 'luck'}})


def test_every_template_has_a_defense():
    for template in TEMPLATES.values():
        assert template.rules.defense is not None
        assert template.rules.defense.ability in [ability.key for ability in template.rules.abilities]


# --- 옛 판과 마이그레이션 ---


def test_an_old_snapshot_keeps_the_fixed_difficulty():
    upgraded = upgrade_from_69({'format': 69, 'rulebook': {'rules': {'die': 20}}})

    assert upgraded == {'format': 70, 'rulebook': {'rules': {'die': 20, 'defense': None}}}
    assert UPGRADES[69] is upgrade_from_69


def load_migration():
    path = next(Path('migrations/versions').glob('*_rulebook_defense.py'))
    spec = importlib.util.spec_from_file_location('rulebook_defense_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_fills_the_defense_once_and_undoes():
    migration = load_migration()
    abilities = [{'key': 'body'}, {'key': 'agility'}, {'key': 'mind'}]
    horror = {'template': 'horror', 'abilities': abilities, 'initiative_ability': 'mind'}
    unknown = {'template': 'mine', 'abilities': abilities, 'initiative_ability': 'mind'}
    bare = {'template': 'mine', 'abilities': abilities, 'initiative_ability': None}
    chosen = {**horror, 'defense': {'ability': 'body'}}

    filled = [migration.with_defense(rules)['defense'] for rules in (horror, unknown, bare)]

    assert filled == [{'ability': 'agility'}, {'ability': 'mind'}, {'ability': 'body'}]
    assert migration.with_defense(chosen) == chosen
    assert migration.without_defense(migration.with_defense(horror)) == horror


# --- 룰북 API ---


async def test_the_rulebook_changes_its_defense(client: AsyncClient, signing_key):
    me = turns.bearer(signing_key, turns.ME)
    url = f'{API_PREFIX}/rulebooks'
    made = await client.post(url, json=asset_body(url, {'title': '규칙'}), headers=me)
    rulebook = made.json()

    changed = await client.patch(f'{url}/{rulebook["id"]}', json={'defense': {'ability': 'con'}}, headers=me)
    refused = await client.patch(f'{url}/{rulebook["id"]}', json={'defense': {'ability': 'luck'}}, headers=me)

    assert rulebook['rules']['defense'] == {'ability': 'dex'}
    assert changed.json()['rules']['defense'] == {'ability': 'con'}
    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 몬스터의 차례 ---

# 차례의 주사위(엘프, 쥐). 쥐가 먼저 친다
LATE, EARLY = 1, 20
ANY = 10


async def rat_turn(session: AsyncSession, table: dict) -> dict:
    found = await turns.turns_of(session, table)
    return next(turn for turn in found if turn['kind'] == 'monster')['outcome']


async def test_the_character_rolls_to_hold_off_the_bite(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    table = await turns.start_table(client, me)
    # 쥐의 물기 13 대 엘프의 민첩 12 → 맞는다. 피해 3. 그 뒤 엘프의 판정
    dice = turns.load_dice(app, [LATE, EARLY, 13, 12, 3, ANY])

    await turns.declare(client, me, table, turns.REST, turns.rest())
    await narrated()

    assert dice.remaining == 0
    outcome = await rat_turn(session, table)
    assert (outcome['success'], outcome['total'], outcome['target']) == (True, 13, 13)
    defense = outcome['defense']
    assert (defense['ability'], defense['roll'], defense['total'], defense['success']) == ('dex', 12, 12, False)
    assert outcome['effect']['amount'] == 3


async def test_a_tie_holds_and_the_attack_may_name_its_defense(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    table = await turns.start_table(client, me, attacks=[{**turns.BITE, 'defense': 'con'}])
    dice = turns.load_dice(app, [LATE, EARLY, 13, 13, ANY])

    await turns.declare(client, me, table, turns.REST, turns.rest())
    await narrated()

    assert dice.remaining == 0
    outcome = await rat_turn(session, table)
    assert (outcome['success'], outcome['effect'], outcome['defense']['ability']) == (False, None, 'con')
    assert outcome['defense']['success'] is True


async def test_a_bystander_rolls_to_hold_off_the_monster(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    world = await bystanders.healer_table(client, me)
    # 쥐가 약사를 고른다. 물기 13 대 약사의 민첩 12 → 맞는다. 피해 3. 그 뒤 엘프의 판정
    dice = turns.load_dice(app, [LATE, EARLY, bystanders.HEALER, 13, 12, 3, ANY])

    await bystanders.act(client, me, world, narrated)

    assert dice.remaining == 0
    outcome = await bystanders.rat_turn(session, world)
    assert (outcome['target_name'], outcome['success'], outcome['defense']['roll']) == ('약사', True, 12)
    assert outcome['npc_effect']['amount'] == 3


async def test_a_fighting_npc_meets_the_characters_roll(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, npc_fights.ME)
    world = await npc_fights.armed_and_fighting(client, app, me, narrated)
    # 라운드 2. 부채 후리기 12 대 엘프의 민첩 12 → 막는다
    dice = turns.load_dice(app, [12, 12])

    await npc_fights.laugh(client, me, world)
    await narrated()

    assert dice.remaining == 0
    (turn,) = npc_fights.npc_turns(await turns.turns_of(session, world['table'], 2))
    outcome = turn['outcome']
    assert (outcome['success'], outcome['effect'], outcome['defense']['success']) == (False, None, True)
