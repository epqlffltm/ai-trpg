# trpg-server/tests/test_check_styles.py

"""
판정 방식(#404)을 검증한다. 주사위 여럿을 굴려 더하는 규칙(2d6)과, 눈이 기량 이하이면 성공인 규칙(d100 under).

규칙의 모양(app/engine/ruleset.py 의 Roll), 판정(app/engine/check.py), 죽음의 굴림과 되살아나기, 선공을 가르는 굴림,
옛 판과 마이그레이션, 룰북 API 로 굴림을 고르는 것을 본다. 주사위는 정해진 눈을 낸다.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError

from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_68
from app.engine import death
from app.engine.check import find_difficulty, harder_by, miss_by, resolve, resolve_hindered
from app.engine.dice import ScriptedDice
from app.engine.injury import Hindrance
from app.engine.ruleset import RollStyle, Ruleset
from app.engine.templates import SRD5
from app.rounds import initiative
from app.rounds.initiative import Turn, TurnKind
from tests import test_monster_injuries as injuries

TEMPLATE = SRD5.model_dump(mode='json')
KEYS = [difficulty['key'] for difficulty in TEMPLATE['difficulties']]
# 어려울수록 기량이 깎인다. 보통은 그대로다
SHIFTS = {'very_easy': 20, 'easy': 10, 'medium': 0, 'hard': -20, 'very_hard': -40}
assert set(SHIFTS) == set(KEYS)


def rules_with(**changes) -> Ruleset:
    """SRD5 에서 몇 칸만 바꾼 규칙."""
    return Ruleset.model_validate({**TEMPLATE, **changes})


TWO_D6 = rules_with(die=6, roll={'count': 2, 'style': 'over', 'shifts': {}}, rest=None, death_save=None)
D100 = rules_with(
    die=100,
    roll={'count': 1, 'style': 'under', 'shifts': SHIFTS},
    armor=None,
    death_save={**TEMPLATE['death_save'], 'target': 50},
)
NO_HINDRANCE = Hindrance(penalty=0, disadvantage=False, injuries=())


# --- 규칙의 모양 ---


def test_the_templates_roll_one_die_over():
    assert (SRD5.roll.count, SRD5.roll.style, SRD5.roll.shifts) == (1, RollStyle.OVER, {})


def test_over_takes_no_shifts():
    with pytest.raises(ValidationError, match='shifts'):
        rules_with(roll={'count': 1, 'style': 'over', 'shifts': {'medium': 0}})


def test_under_needs_a_shift_for_every_difficulty_and_no_other():
    missing = {key: value for key, value in SHIFTS.items() if key != 'hard'}

    with pytest.raises(ValidationError, match='shifts'):
        rules_with(armor=None, roll={'count': 1, 'style': 'under', 'shifts': missing})
    with pytest.raises(ValidationError, match='shifts'):
        rules_with(armor=None, roll={'count': 1, 'style': 'under', 'shifts': {**SHIFTS, 'odd': 0}})


def test_under_cannot_have_armor_yet():
    with pytest.raises(ValidationError, match='armor'):
        rules_with(die=100, roll={'count': 1, 'style': 'under', 'shifts': SHIFTS})


def test_the_death_save_must_be_reachable_by_the_sum():
    # 2d6 의 가장 큰 합은 12 다. 목표 12 는 닿고 13 은 닿지 않는다
    reachable = rules_with(
        die=6,
        roll={'count': 2, 'style': 'over', 'shifts': {}},
        rest=None,
        death_save={**TEMPLATE['death_save'], 'target': 12},
    )

    assert reachable.death_save.target == 12
    with pytest.raises(ValidationError, match='죽음의 굴림'):
        rules_with(
            die=6,
            roll={'count': 2, 'style': 'over', 'shifts': {}},
            rest=None,
            death_save={**TEMPLATE['death_save'], 'target': 13},
        )


def test_under_needs_the_target_at_least_the_smallest_sum():
    # 3d6 under 의 가장 작은 합은 3 이다. 목표 2 이하는 성공할 수 없다
    with pytest.raises(ValidationError, match='죽음의 굴림'):
        rules_with(
            die=6,
            armor=None,
            rest=None,
            roll={'count': 3, 'style': 'under', 'shifts': SHIFTS},
            death_save={**TEMPLATE['death_save'], 'target': 2},
        )


# --- 판정 ---


def test_two_dice_are_added_before_the_modifier():
    medium = find_difficulty(TWO_D6, 'medium')

    check = resolve(TWO_D6, 14, medium, ScriptedDice([3, 4]))

    # 3 + 4 에 점수 14 의 보정 +2
    assert (check.roll, check.faces, check.modifier, check.total, check.style) == (7, (3, 4), 2, 9, 'over')
    assert check.success is (medium.target <= 9)


def test_under_succeeds_when_the_roll_is_at_most_the_skill():
    medium = find_difficulty(D100, 'medium')

    made = resolve(D100, 45, medium, ScriptedDice([45]))
    missed = resolve(D100, 45, medium, ScriptedDice([46]))

    assert (made.roll, made.total, made.target, made.success, made.style) == (45, 45, 45, True, 'under')
    assert (missed.target, missed.success) == (45, False)
    assert (miss_by(made), miss_by(missed)) == (0, 1)


def test_a_hard_difficulty_takes_from_the_skill():
    hard = find_difficulty(D100, 'hard')

    check = resolve(D100, 45, hard, ScriptedDice([30]))

    assert (check.modifier, check.target, check.success) == (-20, 25, False)


def test_under_disadvantage_keeps_the_higher_roll():
    medium = find_difficulty(D100, 'medium')
    hurt = Hindrance(penalty=5, disadvantage=True, injuries=())

    hindered = resolve_hindered(D100, 45, medium, ScriptedDice([10, 42]), hurt, bonus=2)

    # 불리하면 나쁜 눈(큰 눈)을 쓴다. 기량은 45 - 5 + 2
    assert hindered.rolls == (10, 42)
    assert (hindered.check.roll, hindered.check.target, hindered.check.success) == (42, 42, True)


def test_over_disadvantage_still_keeps_the_lower_sum():
    medium = find_difficulty(TWO_D6, 'medium')
    hurt = Hindrance(penalty=0, disadvantage=True, injuries=())

    hindered = resolve_hindered(TWO_D6, 10, medium, ScriptedDice([6, 6, 1, 2]), hurt)

    assert (hindered.rolls, hindered.check.faces, hindered.check.roll) == ((12, 3), (1, 2), 3)


def test_a_raised_target_makes_under_harder_by_the_same_amount():
    medium = find_difficulty(D100, 'medium')
    raised = medium.model_copy(update={'target': medium.target + 5})

    check = resolve_hindered(D100, 45, raised, ScriptedDice([41]), NO_HINDRANCE).check

    assert harder_by(D100, raised) == 5
    assert (check.target, check.success) == (40, False)


# --- 판정 말고 굴리는 것 ---


def test_the_death_save_follows_the_style():
    under = death.roll_death_save(D100, 0, 0, ScriptedDice([50]))
    over = death.roll_death_save(D100, 0, 0, ScriptedDice([51]))

    assert (under.roll, under.success) == (50, True)
    assert over.success is False


def test_the_death_save_adds_the_dice():
    rules = rules_with(
        die=6,
        roll={'count': 2, 'style': 'over', 'shifts': {}},
        rest=None,
        death_save={**TEMPLATE['death_save'], 'target': 7},
    )

    rolled = death.roll_death_save(rules, 0, 0, ScriptedDice([3, 4]))

    assert (rolled.roll, rolled.success) == (7, True)


def tied(name: str) -> Turn:
    member = SimpleNamespace(character_name=name)
    return Turn(TurnKind.PC, member, None, False, 10)


def test_under_breaks_ties_with_the_lower_roll_first():
    ordered = initiative.order_turns([tied('하나'), tied('둘')], D100, ScriptedDice([70, 20]))

    assert [turn.member.character_name for turn in ordered] == ['둘', '하나']
    assert [turn.tiebreak for turn in ordered] == [20, 70]


# --- 옛 판과 마이그레이션 ---


def test_an_old_snapshot_rolls_one_die_over():
    upgraded = upgrade_from_68({'format': 68, 'rulebook': {'rules': {'die': 20}}})

    roll = {'count': 1, 'style': 'over', 'shifts': {}}
    assert upgraded == {'format': 69, 'rulebook': {'rules': {'die': 20, 'roll': roll}}}
    assert UPGRADES[68] is upgrade_from_68


def load_migration():
    path = next(Path('migrations/versions').glob('*_check_rolls.py'))
    spec = importlib.util.spec_from_file_location('check_rolls_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_fills_the_roll_once_and_undoes():
    migration = load_migration()
    old = {'die': 20}

    filled = migration.with_roll(old)

    assert filled == {'die': 20, 'roll': {'count': 1, 'style': 'over', 'shifts': {}}}
    assert migration.with_roll(filled) == filled
    assert migration.without_roll(filled) == old
    assert Ruleset.model_validate({**TEMPLATE, 'roll': migration.ROLL}).roll == SRD5.roll


# --- 룰북 API ---

CLEAN = pytest.mark.usefixtures('clean_tables')
me = injuries.me
UNDER = {'count': 1, 'style': 'under', 'shifts': SHIFTS}


@CLEAN
async def test_a_rulebook_may_roll_d100_under_without_armor(client: AsyncClient, me: dict):
    rulebook = await injuries.post(client, injuries.RULEBOOKS_URL, me, title='백분율', die=100, roll=UNDER, armor=None)

    assert (rulebook['rules']['die'], rulebook['rules']['roll'], rulebook['rules']['armor']) == (100, UNDER, None)


@CLEAN
async def test_under_with_the_templates_armor_is_refused_by_the_roll(client: AsyncClient, me: dict):
    rulebook = await injuries.post(client, injuries.RULEBOOKS_URL, me, title='룰북')
    url = f'{injuries.RULEBOOKS_URL}/{rulebook["id"]}'

    refused = await client.patch(url, json={'die': 100, 'roll': UNDER}, headers=me)
    changed = await client.patch(url, json={'die': 100, 'roll': UNDER, 'armor': None}, headers=me)

    assert (refused.status_code, refused.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'roll')
    assert changed.status_code == status.HTTP_200_OK, changed.text
    assert changed.json()['rules']['roll']['style'] == 'under'


@CLEAN
async def test_a_die_the_death_save_cannot_reach_is_refused(client: AsyncClient, me: dict):
    rulebook = await injuries.post(client, injuries.RULEBOOKS_URL, me, title='룰북')

    response = await client.patch(f'{injuries.RULEBOOKS_URL}/{rulebook["id"]}', json={'die': 6}, headers=me)

    assert (response.status_code, response.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'die')
