# trpg-server/tests/test_injury_ticks.py

"""
짧은 부상(상태 이상)의 라운드마다의 피해와 다시 걸림(#254)을 검증한다.

판은 지하 수로(tests/test_monster_combat.py 의 맵과 몬스터)에, srd5 의 부상들과 출혈(bleeding)을 단 룰북이다.
출혈은 3 라운드짜리 짧은 부상이고 라운드마다 light(1d4)의 피해를 입힌다. 성질은 없다.
독 안개(poison_fog)는 독의 성질의 light 피해를 입히는 2 라운드짜리다.
부상은 행동을 거치지 않고 DB 에 바로 넣는다(입히는 길은 다른 테스트가 본다). 그 라운드가 닫힐 때 걸린 것으로 적는다.

보는 것.
  - 규칙: 짧은 것에만 적는다. 등급과 성질은 규칙에 있어야 한다
  - 다시 걸림: 짧은 것은 하나로 남고 풀릴 라운드를 새로 센다. 수치의 문턱으로 생긴 것은 새로 세지 않는다
  - 테이블: 걸린 라운드에는 깎지 않고, 다음 라운드부터 풀릴 라운드까지 라운드마다 깎는다. 이벤트와 서술.
    0 이 되면 쓰러지고 그 라운드에는 죽음의 굴림을 굴리지 않는다. 쓰러진 쪽은 깎지 않는다. 몬스터도 깎인다
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.rounds import injuries as round_injuries
from app.rounds import injury_ticks, prompt
from app.rounds.narrator import HurtNote
from app.tables.injuries import Moment
from app.tables.models import InjurySource, TableInjury, TableSheet
from tests import test_monster_combat as combat
from tests.test_npc_actions import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = combat.ME
me = combat.me
post = combat.post
table_url = combat.table_url
declare = combat.declare
events_of = combat.events_of
load_dice = combat.load_dice

BLEEDING = {
    'key': 'bleeding',
    'name': '출혈',
    'fact': '상처에서 피가 흐른다.',
    'healing': 'rounds',
    'rounds': 3,
    'damage': {'magnitude': 'light'},
}
POISON_FOG = {
    'key': 'poison_fog',
    'name': '독 안개',
    'fact': '숨이 막힌다.',
    'healing': 'rounds',
    'rounds': 2,
    'natures': ['poison'],
    'damage': {'magnitude': 'light', 'nature': 'poison'},
}
WAIT = '숨을 고른다.'


def injuries_of(*extra: dict) -> list[dict]:
    """srd5 의 부상들에 몇 개를 더한 것. 부상 표가 srd5 의 부상들을 가리킨다."""
    return [*[one.model_dump(mode='json') for one in SRD5.injuries], *extra]


def ruleset_with(*extra: dict) -> Ruleset:
    return Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'injuries': injuries_of(*extra)})


async def start(client: AsyncClient, me: dict, extra: tuple[dict, ...] = (BLEEDING, POISON_FOG)) -> dict:
    """
    srd5 의 부상들에 extra(기본은 출혈과 독 안개)를 단 룰북으로 지하 수로를 혼자 시작한다.

    수로 입구에 쥐 한 마리가 있다.
    """
    lorebook = await post(client, combat.LOREBOOKS_URL, me, title='지하 수로')
    entries = f'{combat.LOREBOOKS_URL}/{lorebook["id"]}/entries'
    gate = await post(client, entries, me, name='수로 입구', kind='place')
    bestiary = await post(client, combat.BESTIARIES_URL, me, title='지하 수로의 것들')
    rat = await post(client, f'{combat.BESTIARIES_URL}/{bestiary["id"]}/monsters', me, name='수로 쥐', kind='beast')
    rulebook = await post(
        client,
        combat.RULEBOOKS_URL,
        me,
        title='피 흘리는 룰북',
        template='srd5',
        injuries=injuries_of(*extra),
    )
    scenario = await post(
        client,
        combat.SCENARIOS_URL,
        me,
        title='지하 수로',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        bestiary_ids=[bestiary['id']],
        openings=['물 떨어지는 소리가 난다.'],
        default_sheet=combat.SHEET,
        monster_sheets=[{'monster_id': rat['id'], 'sheet': combat.RAT_SHEET}],
        start_place=gate['id'],
        encounters=[{'place_id': gate['id'], 'monster_id': rat['id'], 'count': 1}],
    )
    await post(client, f'{combat.SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, combat.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def inflict(session: AsyncSession, table: dict, key: str, ends: int, **owner: uuid.UUID) -> None:
    """1 라운드에 걸린 짧은 부상 하나를 DB 에 넣는다. owner 는 sheet_id 나 monster_id 다."""
    row = TableInjury(
        table_id=uuid.UUID(table['id']),
        injury=key,
        source=InjurySource.ITEM,
        round_number=1,
        ends_after_round=ends,
        **owner,
    )
    session.add(row)
    await session.commit()


async def my_sheet_id(session: AsyncSession) -> uuid.UUID:
    return await session.scalar(select(TableSheet.id).where(TableSheet.user_id == ME))


async def my_hp(client: AsyncClient, headers: dict, table: dict) -> int:
    response = await client.get(table_url(table), headers=headers)
    return response.json()['members'][0]['sheet']['hp']


async def set_my_hp(session: AsyncSession, hp: int) -> None:
    await session.execute(text('UPDATE table_sheets SET hp = :hp WHERE user_id = :user_id'), {'hp': hp, 'user_id': ME})
    await session.commit()


# --- 규칙 ---


def test_damage_is_written_only_on_a_short_injury():
    assert ruleset_with(BLEEDING).injuries[-1].damage.magnitude == 'light'
    lasting = {**BLEEDING, 'healing': 'heals', 'rounds': None, 'heal_minutes': 60}

    with pytest.raises(ValidationError, match='damage 는 짧은 부상'):
        ruleset_with(lasting)


@pytest.mark.parametrize(
    ('damage', 'message'),
    [({'magnitude': 'huge'}, '등급'), ({'magnitude': 'light', 'nature': 'acid'}, '성질')],
)
def test_the_damage_points_at_what_the_rules_have(damage: dict, message: str):
    with pytest.raises(ValidationError, match=message):
        ruleset_with({**BLEEDING, 'damage': damage})


# --- 다시 걸림 ---

RULES = ruleset_with(BLEEDING)
TABLE = uuid.uuid4()


def test_a_short_injury_caught_again_is_counted_anew():
    rows: list[TableInjury] = []
    round_injuries.wound(RULES, 'bleeding', InjurySource.ITEM, {}, rows, TABLE, Moment(1, 0, 10))

    again = round_injuries.wound(RULES, 'bleeding', InjurySource.ITEM, {}, rows, TABLE, Moment(2, 0, 10))

    # 하나로 남고 풀릴 라운드가 새로 세어진다. 효과가 둘로 겹치지 않는다
    assert [(row.injury, row.ends_after_round) for row in rows] == [('bleeding', 5)]
    assert (again['injury'], again['ends_after_round'], again['recounted']) == ('bleeding', 5, True)


def test_an_item_or_an_attack_counts_a_short_injury_anew():
    rows: list[TableInjury] = []
    round_injuries.take_from_item(RULES, 'bleeding', rows, TABLE, Moment(1, 0, 10))

    again = round_injuries.take_from_item(RULES, 'bleeding', rows, TABLE, Moment(3, 0, 10))

    assert [row.ends_after_round for row in rows] == [6]
    assert again['injury'] == 'bleeding'


def test_an_injury_held_by_a_threshold_is_not_counted_anew():
    # 수치의 문턱으로 생긴 것(#804)은 풀릴 라운드가 없다. 라운드로 세게 바꾸지 않는다
    held = TableInjury(injury='bleeding', source=InjurySource.RESOURCE, round_number=1, ends_after_round=None)
    rows = [held]

    again = round_injuries.take_from_item(RULES, 'bleeding', rows, TABLE, Moment(2, 0, 10))

    assert (rows, held.ends_after_round, again['injury']) == ([held], None, None)


# --- 테이블 ---


async def test_bleeding_hurts_each_round_after_it_was_caught(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await start(client, me)
    await inflict(session, table, 'bleeding', ends=3, sheet_id=await my_sheet_id(session))

    # 1 라운드에 걸렸다. 1 라운드가 닫힐 때는 깎지 않는다
    load_dice(app, [])
    await declare(client, me, table, WAIT)
    await narrated()
    assert await my_hp(client, me, table) == 10

    narrator = RecordingNarrator()
    app.state.narrator = narrator
    load_dice(app, [3])
    await declare(client, me, table, WAIT)
    await narrated()
    load_dice(app, [2])
    await declare(client, me, table, WAIT)
    await narrated()

    # 2, 3 라운드에 깎이고 3 라운드가 닫힐 때 풀렸다. 4 라운드에는 깎지 않는다
    assert await my_hp(client, me, table) == 5
    load_dice(app, [])
    await declare(client, me, table, WAIT)
    await narrated()
    hurt = await events_of(client, me, table, 'injury_hurt')
    assert [(one['payload']['round'], one['payload']['injury']) for one in hurt] == [(2, 'bleeding'), (3, 'bleeding')]
    assert hurt[0]['payload'] == {'round': 2, 'user_id': str(ME), 'character_name': '엘프', 'injury': 'bleeding'}
    changed = await events_of(client, me, table, 'hp_changed')
    assert [one['caused_by_sequence'] for one in changed] == [one['sequence'] for one in hurt]
    assert [(one['payload']['before'], one['payload']['after']) for one in changed] == [(10, 7), (7, 5)]
    first = narrator.requests[0]
    assert first.moves[0].hurt_by == [HurtNote(name='출혈', amount=3)]
    assert '[상태의 피해: 출혈 3]' in '\n'.join(message.content for message in prompt.build_messages(first))


async def test_a_bleeding_character_falls_and_rolls_no_death_save_that_round(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await start(client, me)
    await inflict(session, table, 'bleeding', ends=3, sheet_id=await my_sheet_id(session))
    await declare(client, me, table, WAIT)
    await narrated()
    await set_my_hp(session, 2)

    # 2 로 떨어져 쓰러졌다. 쓰러짐에 부상 표를 굴린다(srd5 의 1 은 부상이 없다)
    dice = load_dice(app, [4, 1])
    await declare(client, me, table, WAIT)
    await narrated()

    assert (await my_hp(client, me, table), dice.remaining) == (0, 0)
    assert await events_of(client, me, table, 'death_save_rolled') == []

    # 쓰러진 쪽은 깎지 않는다. 3 라운드에는 죽음의 굴림만 굴린다
    dice = load_dice(app, [15])
    await declare(client, me, table, WAIT)
    await narrated()
    assert dice.remaining == 0
    assert len(await events_of(client, me, table, 'injury_hurt')) == 1


async def test_a_monster_falls_to_its_poison(
    client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession, narrated
):
    table = await start(client, me)
    rat = await combat.monster_named(client, me, table, '수로 쥐')
    await inflict(session, table, 'poison_fog', ends=2, monster_id=uuid.UUID(rat['id']))
    await declare(client, me, table, WAIT)
    await narrated()

    # 독의 피해 4, 쓰러짐에 굴리는 부상 표 1(부상 없음)
    dice = load_dice(app, [4, 1])
    await declare(client, me, table, WAIT)
    await narrated()

    # 쥐(최대 HP 4)는 독의 피해 4 로 쓰러졌다
    assert dice.remaining == 0
    assert await combat.state_of(session, rat['id']) == (0, 'downed')
    (hurt,) = await events_of(client, me, table, 'injury_hurt')
    assert hurt['payload'] == {'round': 2, 'monster_id': rat['id'], 'name': '수로 쥐', 'injury': 'poison_fog'}
    (changed,) = await events_of(client, me, table, 'monster_changed')
    assert changed['caused_by_sequence'] == hurt['sequence']


# --- 작은 함수들 ---


def test_only_an_injury_caught_before_this_round_ticks():
    row = SimpleNamespace(ended_at=None, ends_after_round=3, round_number=1)

    assert injury_ticks.is_ticking(row, 2)
    assert not injury_ticks.is_ticking(row, 1)
    assert not injury_ticks.is_ticking(SimpleNamespace(ended_at=None, ends_after_round=None, round_number=1), 2)
