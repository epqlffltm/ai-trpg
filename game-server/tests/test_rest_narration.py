# game-server/tests/test_rest_narration.py

"""
쉬기를 서술자에게 넘기는 것(#285 서술, narration-27)을 검증한다.

셋을 본다.
  - 줄: 쉰 결과, 깨진 휴식, 되살아나기, 저절로 회복이 한 줄씩 붙는다. HP 의 숫자는 엔진의 값이다.
  - 넘기기: 라운드를 닫을 때 굳힌 각자 한 일에 쉬기의 결과가 들어 서술자에게 간다. 옛 라운드도 읽힌다.
  - 다루는 법: 쉬기나 되살아나기가 있는 라운드에만 붙는다.
"""

from dataclasses import asdict, replace

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds import move_lines, narration_request, prompt
from app.rounds.narrator import Move, RecoveryNote, RestNote, RevivalNote
from evals.state import cases
from tests import test_rests as rest_tests
from tests.test_character_death import LAUGH, ME, declare, knock_me_down, load_dice, start_duo
from tests.test_rests import LONG, NAP, SHORT, SLEEP, make_stable, set_hp
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

# 쉬기 테스트의 픽스처를 그대로 쓴다. 방장(엘프)과 함께 앉는 사람(영애)
me = rest_tests.me
friend = rest_tests.friend


# --- 줄 ---


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (RestNote('long', True, before=2, after=10, max_hp=10), '(쉬기: 긴 휴식, HP 2 → 10/10)'),
        (RestNote('short', True, before=3, after=8, max_hp=10), '(쉬기: 짧은 휴식, HP 3 → 8/10)'),
        (
            RestNote('short', False, reason='hurt', before=7, after=7, max_hp=10),
            '(쉬기: 짧은 휴식. 맞아서 쉬지 못했다)',
        ),
        (RestNote('long', False, reason='downed'), '(쉬기: 긴 휴식. 쓰러져 쉬지 못했다)'),
        (RestNote('long', False, reason='dead'), '(쉬기: 긴 휴식. 죽어 쉬지 못했다)'),
    ],
)
def test_the_rest_is_told_in_one_line(note: RestNote, line: str):
    assert move_lines.describe_rest(note) == line


def test_revival_and_recovery_are_told_in_one_line():
    assert move_lines.describe_revival(RevivalNote(True, 1)) == '(되살아나기: 오래 쉬어 정신이 돌아왔다, HP 1)'
    assert move_lines.describe_revival(RevivalNote(False, 0)) == '(되살아나기: 아직 깨어나지 못했다. 고비는 넘겼다)'
    assert move_lines.describe_recovery(RecoveryNote(3, 8, 10)) == '(시간이 지나 회복: HP 3 → 8/10)'


def test_the_lines_follow_the_move():
    move = Move(
        '엘프',
        NAP,
        rest=RestNote('short', True, before=3, after=8, max_hp=10),
        recovery=RecoveryNote(8, 9, 10),
    )

    assert move_lines.describe_move(move) == (
        f'엘프: {NAP} (쉬기: 짧은 휴식, HP 3 → 8/10) (시간이 지나 회복: HP 8 → 9/10)'
    )


def test_a_round_frozen_before_resting_is_still_read():
    old = asdict(Move('엘프', LAUGH))
    for key in ('rest', 'revival', 'recovery'):
        del old[key]

    (move,) = narration_request.read_moves([old])

    assert (move.rest, move.revival, move.recovery) == (None, None, None)


# --- 넘기기 ---


async def test_the_narrator_hears_the_rest(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start_duo(client, me, friend)
    await set_hp(session, ME, 3)
    load_dice(app, [5])

    await declare(client, me, table, NAP, SHORT)
    await declare(client, friend, table, LAUGH)
    await narrated()

    (request,) = narrator.requests
    mine = next(move for move in request.moves if move.character_name == '엘프')
    assert mine.rest == RestNote('short', True, before=3, after=8, max_hp=10)
    # 쉰 만큼 [시각]의 흐르는 시간도 길다
    assert request.clock.passes_minutes == 60


async def test_the_narrator_hears_the_revival(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await make_stable(session)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    load_dice(app, [15])

    await declare(client, friend, table, SLEEP, LONG)
    await narrated()

    (request,) = narrator.requests
    mine = next(move for move in request.moves if move.character_name == '엘프')
    assert mine.revival == RevivalNote(success=True, hp=1)
    assert mine.downed is False


# --- 다루는 법 ---


def test_the_rest_note_comes_only_with_a_rest():
    resting = cases.REST_BROKEN.request
    quiet = replace(resting, moves=[Move('리엔', LAUGH)], turns=[])

    assert prompt.REST_NOTE in prompt.round_text(resting)
    assert prompt.REST_NOTE in prompt.round_text(cases.REST_NIGHT.request)
    assert prompt.REST_NOTE not in prompt.round_text(quiet)
