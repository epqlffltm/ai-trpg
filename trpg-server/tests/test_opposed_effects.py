# trpg-server/tests/test_opposed_effects.py

"""
피해 없이 해로운 효과로 맞히는 판정도 맞서는 굴림이다(#254)를 검증한다.

독침처럼 부상만 입히는 기술과 물건은 행동(CheckAction)에 겨눈 칸이 없다. 부르는 쪽이 맞을 쪽을 준다
(app/rounds/item_targets.py 의 effect_target). 그 쪽이 규칙의 막는 능력치로 굴리고(app/rounds/checks.py),
방어 태세면 판정이 불리하다. 피해나 회복을 겨눈 판정은 행동의 칸이 정한다.

판은 수로다. 기술(tests/test_skill_targets.py)의 독침, 물건 쓰기(tests/test_item_effects.py)의 기절 가루,
던지기(tests/test_item_throws.py)의 연막탄에 중독을 붙인 것이다. 셋 다 룰북의 맞히는 판정(민첩·보통)이다.
캐릭터와 악역영애와 수로 쥐의 민첩은 10(보정 0)이고, srd5 의 막는 능력치는 민첩이다. 보통은 기본 난이도라 보정이 없다.
이 파일의 테스트는 막는 규칙을 빼지 않은 룰북을 쓴다(@pytest.mark.opposed, tests/conftest.py).
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.action import CheckAction, SkillAction, ThrowAction
from app.engine.item_effects import DamageEffect, HealEffect, InjureEffect
from app.rounds import checks
from app.rounds.checks import Targeted
from app.rounds.item_targets import effect_target
from tests import test_item_effects as uses
from tests import test_item_throws as throws
from tests import test_skill_targets as skills

pytestmark = [pytest.mark.usefixtures('clean_tables'), pytest.mark.opposed]

ME = skills.ME
me = skills.me
STING = skills.cast


async def test_a_sting_beats_the_person_s_roll_and_poisons(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    world = await skills.start(client, me)
    # 독침 12, 악역영애의 민첩 11. 12 > 11 이라 맞는다
    dice = skills.load_dice(app, [12, 11])

    closing = await skills.declare(client, me, world['table'], skills.CAST, STING('sting', npc=world['lady']['id']))

    assert dice.remaining == 0
    outcome = skills.outcome_of(closing, ME)
    assert (outcome['success'], outcome['roll'], outcome['target']) == (True, 12, 12)
    assert [one['injury'] for one in outcome['skill_use']['injured']] == ['poisoned']


async def test_a_tie_holds_the_sting_off(client: AsyncClient, app: FastAPI, me: dict):
    world = await skills.start(client, me)
    # 둘 다 12. 같으면 막는다. 고정 난이도(목표 15)였다면 이 눈은 어느 쪽이든 같았다
    dice = skills.load_dice(app, [12, 12])

    closing = await skills.declare(client, me, world['table'], skills.CAST, STING('sting', npc=world['lady']['id']))

    assert dice.remaining == 0
    outcome = skills.outcome_of(closing, ME)
    assert (outcome['success'], outcome['target'], outcome['skill_use']['injured']) == (False, 13, [])


async def test_a_low_roll_still_poisons_a_worse_defender(client: AsyncClient, app: FastAPI, me: dict):
    world = await skills.start(client, me)
    # 독침 8 은 고정 난이도(목표 15)면 빗나간다. 악역영애가 3 을 굴려 맞는다
    dice = skills.load_dice(app, [8, 3])

    closing = await skills.declare(client, me, world['table'], skills.CAST, STING('sting', npc=world['lady']['id']))

    assert dice.remaining == 0
    outcome = skills.outcome_of(closing, ME)
    assert (outcome['success'], outcome['target']) == (True, 4)
    assert [one['injury'] for one in outcome['skill_use']['injured']] == ['poisoned']


async def test_stun_powder_is_rolled_against_the_rat(client: AsyncClient, app: FastAPI, me: dict):
    world = await uses.start_table(client, me)
    rat = await uses.monster_named(client, me, world['table'], '수로 쥐')
    # 가루 8 은 고정 난이도면 빗나간다. 쥐가 3 을 굴려 맞는다
    dice = uses.load_dice(app, [8, 3])

    closing = await uses.declare(
        client, me, world['table'], '가루를 뿌린다.', uses.use(world['powder'], monster=rat['id'])
    )

    assert dice.remaining == 0
    outcome = uses.outcome_of(closing)
    assert (outcome['success'], outcome['target']) == (True, 4)
    assert [one['injury'] for one in outcome['item_use']['injured']] == ['stunned']


async def test_a_thrown_poison_is_rolled_against_the_rat(client: AsyncClient, app: FastAPI, me: dict):
    world = await throws.make_world(client, me)
    items = [
        {**item, 'effects': [throws.POISON]} if item['entry_id'] == world['smoke']['id'] else item
        for item in throws.the_items(world)
    ]
    scenario = await throws.make_scenario(client, me, world, items)
    table = await throws.start_from(client, me, world, scenario)
    rat = await throws.monster_named(client, me, table, '수로 쥐 1')
    # 던진 연막탄 12, 쥐 12. 같으면 막는다
    dice = throws.load_dice(app, [12, 12])

    closing = await throws.declare(client, me, table, throws.THROW, throws.throw(world['smoke'], monster=rat['id']))

    assert dice.remaining == 0
    outcome = throws.outcome_of(closing, ME)
    assert (outcome['success'], outcome['target'], outcome['item_throw']['injured']) == (False, 13, [])


# --- 맞을 쪽 ---

POISON = InjureEffect(kind='injure', injury='poisoned')
HURT = DamageEffect(kind='damage', magnitude='light')
MEND = HealEffect(kind='heal', magnitude='light')
PLAIN = CheckAction(kind='check', ability='dex')


def test_only_a_harmful_effect_without_damage_names_who_rolls_against_it():
    person, rat, friend = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    at_person = SkillAction(kind='skill', skill='sting', npc=person)
    at_rat = ThrowAction(kind='throw', item=uuid.uuid4(), monster=rat)
    at_friend = SkillAction(kind='skill', skill='sting', target=friend)

    assert effect_target([POISON], at_person, PLAIN) == Targeted(npc=person)
    assert effect_target([POISON], at_rat, PLAIN) == Targeted(monster=rat)
    assert effect_target([POISON], at_friend, PLAIN) == Targeted(target=friend)
    # 피해를 겨누면 행동의 칸이 정한다. 회복이나 해롭지 않은 효과는 막지 않는다
    harm = CheckAction(kind='check', ability='dex', harm='light', npc=person)
    mend = CheckAction(kind='check', ability='wis', recover='light', npc=person)
    assert effect_target([POISON, HURT], at_person, harm) is None
    assert effect_target([MEND, POISON], at_person, mend) is None
    assert effect_target([MEND], at_person, PLAIN) is None


def test_a_guarding_foe_hinders_an_effect_too():
    rat, ally = uuid.uuid4(), uuid.uuid4()
    judging = SimpleNamespace(defending=frozenset({ally}), foes_guarding=frozenset({rat}))

    assert checks.target_guarded(judging, PLAIN, Targeted(monster=rat)) is True
    assert checks.target_guarded(judging, PLAIN, Targeted(target=ally)) is True
    assert checks.target_guarded(judging, PLAIN, Targeted(npc=uuid.uuid4())) is False
    # 맞을 쪽이 없는 판정(살피기 같은 것)은 방어와 상관없다
    assert checks.target_guarded(judging, PLAIN) is False
