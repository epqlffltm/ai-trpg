# trpg-server/tests/test_injury_escapes.py

"""
짧은 부상(상태 이상)에서 판정으로 벗어나기(#254)를 검증한다.

판은 tests/test_injury_ticks.py 의 지하 수로다. 룰북에 거미줄(webbed)을 단다. 3 라운드짜리 짧은 부상이고,
근력으로 보통(목표 15)에 도전해 벗어난다. 근력 판정에 불리하다. 출혈(bleeding)은 피해만 있고 벗어날 수 없다.
엘프의 능력치는 모두 10(보정 0)이다. 부상은 DB 에 바로 넣는다(1 라운드에 걸린 것으로 적는다).

보는 것.
  - 규칙: 짧은 것에만 적는다. 능력치와 난이도는 규칙에 있어야 한다
  - 테이블: 걸린 라운드와 어차피 풀리는 라운드에는 굴리지 않는다. 그 사이의 라운드마다 굴린다.
    성공하면 바로 풀리고(injury_ended, reason escaped), 실패하면 그대로다. 불리함이 든다. 이벤트와 서술.
    피해를 먼저 입고 나서 굴린다
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds import prompt
from app.rounds.injury_escapes import is_escapable
from tests import test_injury_ticks as ticks
from tests.test_npc_actions import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = ticks.ME
me = ticks.me
declare = ticks.declare
events_of = ticks.events_of
load_dice = ticks.load_dice

WEBBED = {
    'key': 'webbed',
    'name': '거미줄',
    'fact': '끈끈한 거미줄에 감겼다.',
    'healing': 'rounds',
    'rounds': 3,
    'effects': [{'kind': 'disadvantage', 'abilities': ['str']}],
    'escape': {'ability': 'str', 'difficulty': 'medium'},
}
# 벗어날 수 있는 출혈. 피해를 먼저 입고 굴린다
CLOTTING = {**ticks.BLEEDING, 'key': 'clotting', 'name': '굳는 피', 'escape': {'ability': 'con'}}
WAIT = ticks.WAIT


async def webbed_me(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, key: str = 'webbed') -> dict:
    """
    거미줄과 굳는 피를 단 판에서 시작하고, 1 라운드에 걸려 4 라운드가 닫힐 때 풀릴 그 부상을 입힌다.

    1 라운드를 닫는다(걸린 라운드라 굴리지 않는다).
    """
    table = await ticks.start(client, me, (WEBBED, CLOTTING, ticks.BLEEDING))
    await ticks.inflict(session, table, key, ends=4, sheet_id=await ticks.my_sheet_id(session))
    load_dice(app, [])
    await declare(client, me, table, WAIT)
    return table


# --- 규칙 ---


def test_escape_is_written_only_on_a_short_injury():
    assert ticks.ruleset_with(WEBBED).injuries[-1].escape.ability == 'str'
    lasting = {**WEBBED, 'healing': 'heals', 'rounds': None, 'heal_minutes': 60}

    with pytest.raises(ValidationError, match='escape 는 짧은 부상'):
        ticks.ruleset_with(lasting)


@pytest.mark.parametrize('escape', [{'ability': 'luck'}, {'ability': 'str', 'difficulty': 'impossible'}])
def test_the_escape_points_at_what_the_rules_have(escape: dict):
    with pytest.raises(ValidationError, match='벗어나는 판정'):
        ticks.ruleset_with({**WEBBED, 'escape': escape})


# --- 테이블 ---


async def test_a_failed_escape_keeps_the_web_and_a_success_tears_it(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await webbed_me(client, app, me, session)
    await narrated()

    # 2 라운드: 불리해서 두 번 굴려 낮은 눈(18, 5)을 쓴다. 실패
    load_dice(app, [18, 5])
    await declare(client, me, table, WAIT)
    await narrated()
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    # 3 라운드: 16, 19 중 낮은 16 으로 성공. 바로 풀린다
    load_dice(app, [16, 19])
    await declare(client, me, table, WAIT)
    await narrated()

    rolled = await events_of(client, me, table, 'injury_escape_rolled')
    assert [(one['payload']['round'], one['payload']['roll'], one['payload']['success']) for one in rolled] == [
        (2, 5, False),
        (3, 16, True),
    ]
    assert rolled[0]['payload']['hindrance'] == {
        'injuries': ['webbed'],
        'penalty': 0,
        'disadvantage': True,
        'rolls': [18, 5],
    }
    (ended,) = await events_of(client, me, table, 'injury_ended')
    assert ended['payload'] == {
        'round': 3,
        'user_id': str(ME),
        'character_name': '엘프',
        'injury': 'webbed',
        'reason': 'escaped',
    }
    assert ended['caused_by_sequence'] == rolled[1]['sequence']
    (request,) = narrator.requests
    assert request.moves[0].escaped == ['거미줄']
    assert request.moves[0].injuries == []
    assert '[벗어난 상태: 거미줄]' in '\n'.join(message.content for message in prompt.build_messages(request))


async def test_no_roll_on_the_round_it_ends_anyway(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await webbed_me(client, app, me, session)
    await narrated()
    for _ in range(2):
        load_dice(app, [1, 1])
        await declare(client, me, table, WAIT)
        await narrated()

    # 4 라운드가 닫힐 때 어차피 풀린다. 굴리지 않는다
    dice = load_dice(app, [])
    await declare(client, me, table, WAIT)
    await narrated()

    assert dice.remaining == 0
    assert len(await events_of(client, me, table, 'injury_escape_rolled')) == 2
    (ended,) = await events_of(client, me, table, 'injury_ended')
    assert ended['payload']['reason'] == 'expired'


async def test_the_damage_comes_before_the_escape(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await webbed_me(client, app, me, session, key='clotting')
    await narrated()

    # 피해의 눈 3, 그다음 체력 판정 20 으로 벗어났다. 벗어난 라운드에도 그 피해는 입었다
    load_dice(app, [3, 20])
    await declare(client, me, table, WAIT)
    await narrated()

    assert await ticks.my_hp(client, me, table) == 7
    hurt = await events_of(client, me, table, 'injury_hurt')
    rolled = await events_of(client, me, table, 'injury_escape_rolled')
    assert hurt[0]['sequence'] < rolled[0]['sequence']
    assert rolled[0]['payload']['success'] is True


async def test_an_injury_without_an_escape_is_not_rolled(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await webbed_me(client, app, me, session, key='bleeding')
    await narrated()

    dice = load_dice(app, [2])
    await declare(client, me, table, WAIT)
    await narrated()

    assert dice.remaining == 0
    assert await events_of(client, me, table, 'injury_escape_rolled') == []


def test_only_rounds_in_between_are_rolled():
    row = SimpleNamespace(ended_at=None, ends_after_round=4, round_number=1)

    assert [round_number for round_number in range(1, 6) if is_escapable(row, round_number)] == [2, 3]
