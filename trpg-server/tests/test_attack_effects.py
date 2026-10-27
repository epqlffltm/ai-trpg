# trpg-server/tests/test_attack_effects.py

"""
몬스터와 인물의 공격의 효과(#805 ③-b, app/rounds/monster_attacks.py 의 with_effects)를 검증한다.

몬스터의 판은 test_monster_turns.py 의 것이다. 수로 입구에 쥐 한 마리(민첩 14 라 먼저 친다). 시험마다 공격을 바꾼다.
  - 독니: 근력·보통, 가벼운 피해(1d4), 맞히면 중독
  - 독 뿜기: 근력·보통, 피해 없음, 맞히면 중독
세이브는 test_saves.py 의 판이다(세이브 목표 15, 엘프는 몸에 판금 5). 주사위는 판정의 눈을 먼저 쓴다.
중독된 엘프는 판정에 불리하다(눈 둘 중 낮은 것). 그래서 중독된 뒤의 엘프의 판정은 눈 둘을 쓴다.

넷을 본다.
  - 시나리오: 공격의 효과는 부상과 수치의 맞추기뿐이다. 피해 등급은 비울 수 있다.
    피해도 효과도 없는 공격은 받지 않는다.
    효과의 부상은 규칙의 것이고, 맞추는 수치는 캐릭터가 가진 규칙의 수치여야 한다. 아니면 게시의 문제다.
  - 차례: 맞히면 맞은 캐릭터에게 효과가 든다. 빗나가면 들지 않는다. 세이브는 피해만 막는다(효과는 든다).
    피해가 없는 공격은 세이브를 굴리지 않는다.
  - 기록: 공격의 이벤트 뒤에 입힌 부상(injury_gained, source attack)과
    맞춘 수치(resource_changed, source attack)가 잇는다.
  - 서술: 차례의 줄에 입힌 부상과 바뀐 수치를 붙인다. 되돌리는 마이그레이션은 시나리오의 공격에서 효과를 뺀다.
"""

import json
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.publishing import attack_fault
from app.assets.scenarios.schemas import MonsterAttack
from app.engine.ruleset import ResourceHolder, Ruleset
from app.engine.templates import SRD5
from app.rounds.models import Round
from app.rounds.move_lines import describe_monster_turn
from app.rounds.narration_request import to_turn_note
from tests import test_monster_turns as turns
from tests import test_saves as saves
from tests.sheets import make_sheet
from tests.test_attack_costs import rewrite_content
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')

me = turns.me
ME = turns.ME
PASS = turns.PASS
FAIL = turns.FAIL
POISON = {'kind': 'injure', 'injury': 'poisoned'}
FANG = {'name': '독니', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light', 'effects': [POISON]}
SPIT = {'name': '독 뿜기', 'ability': 'str', 'difficulty': 'medium', 'effects': [POISON]}
MANA = {'key': 'mana', 'name': '마나', 'max': {'base': 6}}
DRAIN = {'kind': 'adjust', 'resource': 'mana', 'amount': -2}
FAST_RAT = make_sheet(max_hp=4, dex=14)


async def rat_with(client: AsyncClient, me: dict, attack: dict) -> dict:
    return await turns.start_table(client, me, rat_sheet=FAST_RAT, attacks=[attack])


async def turn_outcome(session: AsyncSession, table: dict) -> dict:
    return (await turns.turns_of(session, table))[0]['outcome']


async def injuries_of(session: AsyncSession, table: dict) -> list[tuple[str, str]]:
    rows = await session.execute(
        text('SELECT injury, source FROM table_injuries WHERE table_id = :id'), {'id': uuid.UUID(table['id'])}
    )
    return [tuple(row) for row in rows.all()]


# --- 시나리오 ---


def test_an_attack_may_be_effects_only():
    attack = MonsterAttack.model_validate(SPIT)

    assert (attack.harm, [one.injury for one in attack.effects]) == (None, ['poisoned'])


@pytest.mark.parametrize(
    'body',
    [
        {k: v for k, v in SPIT.items() if k != 'effects'},
        {**FANG, 'effects': [{'kind': 'heal', 'magnitude': 'light'}]},
        {**FANG, 'effects': [{'kind': 'damage', 'magnitude': 'light'}]},
        {**FANG, 'effects': [POISON, POISON]},
    ],
    ids=['nothing-at-all', 'heal', 'extra-damage', 'twice'],
)
def test_only_injuries_and_adjustments_are_attack_effects(body: dict):
    with pytest.raises(ValidationError):
        MonsterAttack.model_validate(body)


@pytest.mark.parametrize(
    ('effects', 'holders', 'fault'),
    [
        ([POISON], ['characters'], False),
        ([{'kind': 'injure', 'injury': 'cursed'}], ['characters'], True),
        ([DRAIN], ['characters'], False),
        ([DRAIN], ['monsters'], True),
        ([{**DRAIN, 'resource': 'gold'}], ['characters'], True),
    ],
    ids=['known-injury', 'unknown-injury', 'drain', 'drain-not-held-by-characters', 'unknown-resource'],
)
def test_attack_effects_must_fit_the_rules(effects: list, holders: list[str], fault: bool):
    rules = Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'resources': [{**MANA, 'holders': holders}]})
    attack = MonsterAttack.model_validate({**SPIT, 'effects': effects})

    assert attack_fault(rules, attack, ResourceHolder.MONSTERS) is fault


async def test_an_effects_only_attack_is_published(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    table = await rat_with(client, me, SPIT)

    content = (
        await session.execute(text('SELECT content FROM game_tables WHERE id = :id'), {'id': table['id']})
    ).scalar()
    (attack,) = content['monsters'][0]['attacks']
    assert (attack['harm'], attack['effects']) == (None, [POISON])


# --- 차례 ---


async def test_a_poisoned_fang_hurts_and_poisons(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    table = await rat_with(client, me, FANG)
    dice = turns.load_dice(app, [PASS, 3, FAIL, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    outcome = await turn_outcome(session, table)
    assert (outcome['effect']['after'], [one['injury'] for one in outcome['injured']]) == (7, ['poisoned'])
    assert outcome['attack'] == {k: v for k, v in FANG.items() if k != 'effects'}
    assert await injuries_of(session, table) == [('poisoned', 'attack')]
    assert dice.remaining == 0


async def test_a_miss_brings_no_effect(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    table = await rat_with(client, me, FANG)
    turns.load_dice(app, [FAIL, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    assert ((await turn_outcome(session, table))['injured'], await injuries_of(session, table)) == ([], [])


async def test_a_spit_poisons_without_damage(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    table = await rat_with(client, me, SPIT)
    # 피해의 눈이 없다. 쥐의 맞히기, 중독된 엘프의 판정(눈 둘)만 굴린다
    dice = turns.load_dice(app, [PASS, FAIL, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    outcome = await turn_outcome(session, table)
    assert (outcome['effect'], [one['injury'] for one in outcome['injured']]) == (None, ['poisoned'])
    assert await turns.hp_of(session, table) == 10
    assert dice.remaining == 0


async def test_a_spit_on_someone_downed_adds_no_death_failure(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    table = await rat_with(client, me, SPIT)
    await session.execute(text('UPDATE table_sheets SET hp = 0 WHERE table_id = :id'), {'id': uuid.UUID(table['id'])})
    await session.commit()
    turns.load_dice(app, [PASS, 10])

    await turns.declare(client, me, table, turns.REST)

    outcome = await turn_outcome(session, table)
    assert 'downed_strike' not in outcome
    assert [one['injury'] for one in outcome['injured']] == ['poisoned']


async def test_a_drain_lowers_the_character_s_resource(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    table = await rat_with(client, me, SPIT)

    def with_mana(content: dict) -> None:
        """게시한 판의 규칙에 마나를 달고, 쥐의 공격을 마나 빨기로 바꾼다. 게시할 때는 마나가 없어 바꿔 단다."""
        content['rulebook']['rules']['resources'] = [MANA]
        content['monsters'][0]['attacks'] = [{**SPIT, 'name': '마나 빨기', 'effects': [DRAIN]}]

    await rewrite_content(session, table['id'], with_mana)
    turns.load_dice(app, [PASS, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    outcome = await turn_outcome(session, table)
    assert [(one['before'], one['after'], one['user_id']) for one in outcome['resources']] == [(6, 4, str(ME))]
    events = await turns.events_of(client, me, table)
    attacked = next(event for event in events if event['type'] == 'monster_attacked')
    (drained,) = [event for event in events if event['type'] == 'resource_changed']
    assert (drained['payload']['source'], drained['payload']['user_id']) == ('attack', str(ME))
    assert drained['caused_by_sequence'] == attacked['sequence']


async def test_a_save_stops_the_damage_but_not_the_poison(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    claw = [{'name': '독 발톱', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light', 'effects': [POISON]}]
    _, table = await saves.start(client, me, sheet=make_sheet(max_hp=30, dex=14), attacks=claw)
    # 고블린이 먼저. 엘프의 몸(판금 5)에 맞음, 맞히기 15, 세이브 10 + 5 → 막음. 중독된 엘프는 숨는다(판정 1, 1)
    dice = saves.load_dice(app, [saves.BODY, 15, 10, 1, 1])

    body = {'content': '숨는다.', 'action': {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}}
    await client.put(saves.table_url(table, '/rounds/current/declaration'), json=body, headers=me)

    query = select(Round).where(Round.table_id == uuid.UUID(table['id']), Round.number == 1)
    turn = (await session.scalar(query.execution_options(populate_existing=True))).turns[0]['outcome']
    assert (turn['effect'], turn['blow']['save']['saved']) == (None, True)
    assert [one['injury'] for one in turn['injured']] == ['poisoned']
    assert dice.remaining == 0


async def test_a_spit_rolls_no_save(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    spit = [{'name': '독 뿜기', 'ability': 'str', 'difficulty': 'medium', 'effects': [POISON]}]
    _, table = await saves.start(client, me, sheet=make_sheet(max_hp=30, dex=14), attacks=spit)
    # 부위, 맞히기 15 다음은 중독된 엘프의 판정(눈 둘)이다. 세이브의 눈이 없다
    dice = saves.load_dice(app, [saves.BODY, 15, 1, 1])

    body = {'content': '숨는다.', 'action': {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}}
    await client.put(saves.table_url(table, '/rounds/current/declaration'), json=body, headers=me)

    assert dice.remaining == 0


# --- 기록과 서술 ---


async def test_the_poison_is_recorded_after_the_attack(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    table = await rat_with(client, me, FANG)
    turns.load_dice(app, [PASS, 3, FAIL, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    events = await turns.events_of(client, me, table)
    attacked = next(event for event in events if event['type'] == 'monster_attacked')
    (gained,) = [event for event in events if event['type'] == 'injury_gained']
    assert (gained['payload']['injury'], gained['payload']['source']) == ('poisoned', 'attack')
    assert (gained['payload']['user_id'], gained['caused_by_sequence']) == (str(ME), attacked['sequence'])
    stored = await session.execute(text("SELECT payload FROM table_events WHERE type = 'monster_attacked'"))
    payload = stored.scalar_one()
    assert 'injured' not in payload and 'resources' not in payload


def test_the_narrator_hears_the_effects():
    turn = {
        'kind': 'monster',
        'name': '독거미',
        'outcome': {
            'attack': {'name': '독니'},
            'character_name': '엘프',
            'success': True,
            'effect': None,
            'injured': [{'injury': 'poisoned', 'name': '중독'}, {'injury': None, 'name': '기절'}],
            'resources': [{'resource': 'mana', 'name': '마나', 'before': 5, 'after': 3, 'max': 7}],
        },
    }

    line = describe_monster_turn(to_turn_note(turn).monster)

    assert line == '독거미: 엘프에게 독니 (맞음) [입힌 부상: 중독] [수치: 마나 5 → 3/7]'


# --- 마이그레이션 ---


def test_going_back_takes_the_effects_out_of_the_scenario_attacks():
    migration = load_migration('attack_effects')
    sheets = [
        {'monster_id': 'a', 'attacks': [FANG, SPIT]},
        {'entry_id': 'b', 'sheet': {}},
    ]

    back = migration.sheets_without_effects(json.loads(json.dumps(sheets)))

    assert back == [
        {'monster_id': 'a', 'attacks': [{k: v for k, v in FANG.items() if k != 'effects'}]},
        {'entry_id': 'b', 'sheet': {}},
    ]
