# trpg-server/tests/test_waits.py

"""
기다리기(#367, app/rounds/waits.py)를 검증한다. 방장이 다음 걸음을 정하던 것을 대신한다.

모두 기다리면 건너뛰고, 한 사람이라도 다른 일을 하거나 내지 않으면 흐르지 않는 것과 받는 범위는
tests/test_table_clock.py 가 본다. 여기서는 그 밖의 것을 본다.
  - 깨지기: 몬스터 곁에서도 받는다. 맞으면 깨져 시간이 건너뛰지 않는다. 빗나가면 건너뛴다.
  - 서술: 서술자가 기다리기의 결과를 받고, 한 일의 줄에 붙는다. 이 칸이 없던 옛 라운드도 읽는다.
  - 상한: 기다리기의 상한은 시계의 걸음의 상한과 같다.
"""

from dataclasses import asdict

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.assets.models import ROUND_MAX_MINUTES
from app.engine.action import WAIT_MAX_MINUTES
from app.rounds import move_lines
from app.rounds.narration_request import read_moves
from app.rounds.narrator import Move, WaitNote
from tests import test_monster_turns as monster_tests
from tests.test_table_clock import NIGHT_MARCH, start_solo, wait, wait_round
from tests.test_table_items import ME, events_of
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

HOUR = 60
NIGHT = 8 * HOUR


@pytest.fixture
def solo(signing_key) -> dict[str, str]:
    """쥐가 있는 수로에 혼자 앉는 사람의 머리말."""
    return monster_tests.bearer(signing_key, ME)


def wait_outcome(closing: dict) -> dict:
    """닫는 라운드의 응답에서 혼자 앉은 사람의 기다리기의 결과."""
    (declaration,) = closing['declarations']
    return declaration['outcome']['wait']


async def passed_minutes(client: AsyncClient, headers: dict, table: dict) -> int:
    """두 번째 라운드가 열릴 때 흐른 분."""
    _, second = await events_of(client, headers, table, 'round_opened')
    return second['payload']['passed_minutes']


# --- 깨지기 ---


async def test_a_hit_breaks_the_wait(client: AsyncClient, app: FastAPI, solo: dict, narrated):
    # 쥐가 먼저(민첩 14). 물기 20(맞힘), 피해 3. 싸우는 중에 하룻밤을 건너뛰지 않는다
    dice = monster_tests.load_dice(app, [monster_tests.PASS, 3])
    table = await monster_tests.start_table(client, solo, rat_sheet=monster_tests.make_sheet(max_hp=4, dex=14))

    closing = await monster_tests.declare(client, solo, table, '쥐를 지켜보며 밤을 샌다.', wait(NIGHT))
    await narrated()

    assert wait_outcome(closing) == {'minutes': NIGHT, 'waited': False, 'reason': 'hurt'}
    assert await passed_minutes(client, solo, table) == 10
    assert dice.remaining == 0


async def test_a_wait_beside_a_monster_goes_on_when_it_misses(client: AsyncClient, app: FastAPI, solo: dict, narrated):
    # 기다릴 수 없는 곳은 없다. 쥐가 빗나가면(1) 아무도 맞지 않았으니 하룻밤이 흐른다
    dice = monster_tests.load_dice(app, [monster_tests.FAIL])
    table = await monster_tests.start_table(client, solo, rat_sheet=monster_tests.make_sheet(max_hp=4, dex=14))

    closing = await monster_tests.declare(client, solo, table, '쥐를 지켜보며 밤을 샌다.', wait(NIGHT))
    await narrated()

    assert wait_outcome(closing) == {'minutes': NIGHT, 'waited': True, 'reason': None}
    assert await passed_minutes(client, solo, table) == NIGHT
    assert dice.remaining == 0


# --- 서술 ---


async def test_the_narrator_hears_of_the_wait(client: AsyncClient, app: FastAPI, solo: dict, narrated):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start_solo(client, solo, NIGHT_MARCH)

    await wait_round(client, solo, table, NIGHT, narrated)

    (request,) = narrator.requests
    (move,) = request.moves
    assert move.wait == WaitNote(minutes=NIGHT, waited=True, reason=None)
    # 건너뛴 시간은 [시각]에 있다. 3일째 22시에 시작해 4일째 6시에 끝난다
    assert request.clock.passes_minutes == NIGHT


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (WaitNote(minutes=3 * 24 * HOUR, waited=True), '(기다리기: 3일)'),
        (
            WaitNote(minutes=NIGHT, waited=False, reason='not_all'),
            '(기다리기: 8시간. 모두가 기다리지 않아 시간이 건너뛰지 않았다)',
        ),
        (
            WaitNote(minutes=90, waited=False, reason='hurt'),
            '(기다리기: 1시간 30분. 싸움이 벌어져 시간이 건너뛰지 않았다)',
        ),
    ],
    ids=['waited', 'not-all', 'hurt'],
)
def test_the_wait_is_one_line_of_what_was_done(note: WaitNote, line: str):
    move = Move('엘프', '기다린다.', wait=note)

    assert move_lines.describe_wait(note) == line
    assert line in move_lines.describe_move(move)


def test_a_round_fixed_before_waiting_is_read_without_a_wait():
    old = asdict(Move('엘프', '기다린다.'))
    del old['wait']

    (move,) = read_moves([old])

    assert move.wait is None


# --- 상한 ---


def test_the_longest_wait_is_the_longest_step():
    # 늘린 걸음은 table_clocks 의 CHECK(next_step_range)를 넘지 않아야 한다
    assert WAIT_MAX_MINUTES == ROUND_MAX_MINUTES
