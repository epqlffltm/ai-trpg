# trpg-server/tests/test_clock_narration.py

"""
게임 안의 시각이 서술에 들어가는 것(달력 3단계, narration-23)을 검증한다.

셋을 본다.
  - 서술자가 받는 것: 이 라운드가 열린 시각, 다음 라운드가 열릴 때까지 흐를 시간, 그때의 시각.
    모두 기다려 엔진이 늘린 걸음을 그 라운드의 서술이 따른다(서술을 맡길 때 읽는다).
  - 프롬프트: "[시각]"이 퀘스트 뒤, 맵 앞에 붙는다. 시계가 없으면 붙지 않는다.
  - 흐르는 시간이 한 시간을 넘으면 건너뛰라는 말이 붙는다. 흐르지 않으면 그렇다고 적는다.
"""

import uuid
from dataclasses import replace

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.calendar.clock import ClockTime, TimeOfDay, read_time
from app.rounds import prompt, service, time_words
from app.rounds.narrator import ClockNote, Move, NarrationRequest, PlaceNote, QuestNote
from tests.test_round_closing import HeldJobs, started_at
from tests.test_rounds_api import ME, bearer
from tests.test_table_clock import NIGHT_MARCH, declare_wait, next_round, start_solo
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장의 머리말. 혼자 앉는다."""
    return bearer(signing_key, ME)


@pytest.fixture
def recording(app: FastAPI) -> RecordingNarrator:
    """앱의 서술자를 받은 요청을 적어 두는 것으로 바꾼다."""
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    return narrator


@pytest.fixture
def held_jobs(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> HeldJobs:
    """앱이 맡기는 작업(서술)을 돌리지 않게 한다. 닫는 중인 라운드를 세워 둔다."""
    jobs = HeldJobs()
    monkeypatch.setattr(app.state, 'jobs', jobs)
    return jobs


def at(day: int, hour: int, minute: int = 0) -> ClockTime:
    """며칠째 몇 시 몇 분의 시각. 하루의 어느 때는 셈이 정한다."""
    return read_time(((day - 1) * 24 + hour) * 60 + minute)


# --- 서술자가 받는 것 ---


async def test_the_narrator_gets_the_time_of_the_scene(
    client: AsyncClient, me: dict, recording: RecordingNarrator, narrated
):
    table = await start_solo(client, me, NIGHT_MARCH)

    await next_round(client, me, table, narrated)
    await next_round(client, me, table, narrated)

    first, second = recording.requests
    # 첫 라운드는 3일째 22시에 열렸고, 판의 기본(3시간)이 흘러 다음 라운드가 4일째 1시에 열린다
    assert first.clock == ClockNote(now=at(3, 22), ends=at(4, 1), passes_minutes=180)
    assert second.clock == ClockNote(now=at(4, 1), ends=at(4, 4), passes_minutes=180)


async def test_a_wait_reaches_the_narration(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, held_jobs: HeldJobs
):
    table = await start_solo(client, me, NIGHT_MARCH)
    await declare_wait(client, me, table, 8 * 60)
    started = await started_at(app, table)

    # 모두(혼자) 하룻밤을 기다렸다. 닫힐 때 엔진이 늘린 걸음으로 그 라운드의 서술이 새벽에서 맺는다
    request = await service.load_closing_request(session, uuid.UUID(table['id']), 1, started)

    assert request.clock == ClockNote(now=at(3, 22), ends=at(4, 6), passes_minutes=480)
    assert request.clock.ends.time_of_day == TimeOfDay.DAWN


# --- 프롬프트 ---


def make_request(clock: ClockNote | None, quests: list[QuestNote] | None = None) -> NarrationRequest:
    """시각과 퀘스트, 맵에 선 캐릭터 하나만 정한 서술 요청."""
    move = Move('리엔', '바이크를 몬다.', place=PlaceNote(name='휴게소', exits=['톨게이트']))
    request = NarrationRequest(round_number=2, scene='휴게소.', moves=[move])
    return replace(request, clock=clock, quests=quests or [])


def test_the_prompt_tells_when_the_scene_starts_and_ends():
    clock = ClockNote(now=at(3, 22), ends=at(3, 22, 20), passes_minutes=20)

    text = prompt.round_text(make_request(clock, [QuestNote('왕녀 구출', 'active')]))

    assert prompt.CLOCK_TITLE in text
    assert prompt.CLOCK_NOTE in text
    assert '- 장면이 시작하는 때: 3일째 22시 00분(밤)' in text
    assert '- 흐르는 시간: 20분' in text
    assert '- 장면이 끝나는 때: 3일째 22시 20분(밤)' in text
    # 짧으면 건너뛰라고 하지 않는다
    assert prompt.CLOCK_SKIP_NOTE not in text
    # 퀘스트 뒤, 맵 앞이다
    assert text.index(prompt.QUEST_TITLE) < text.index(prompt.CLOCK_TITLE) < text.index(prompt.MAP_TITLE)


def test_a_long_pass_is_skipped_over():
    clock = ClockNote(now=at(3, 22), ends=at(4, 6), passes_minutes=480)

    text = prompt.round_text(make_request(clock))

    assert '- 흐르는 시간: 8시간' in text
    assert '- 장면이 끝나는 때: 4일째 6시 00분(새벽)' in text
    assert prompt.CLOCK_SKIP_NOTE in text


def test_an_hour_is_not_yet_a_skip():
    clock = ClockNote(now=at(1, 8), ends=at(1, 9), passes_minutes=prompt.LONG_PASS_MINUTES)

    assert prompt.CLOCK_SKIP_NOTE not in prompt.round_text(make_request(clock))


def test_no_clock_no_section():
    assert prompt.CLOCK_TITLE not in prompt.round_text(make_request(None))


@pytest.mark.parametrize(
    ('minutes', 'text'),
    [
        (0, time_words.NO_TIME_PASSES),
        (10, '10분'),
        (60, '1시간'),
        (90, '1시간 30분'),
        (8 * 60, '8시간'),
        (24 * 60, '1일'),
        (7 * 24 * 60, '7일'),
        (26 * 60 + 5, '1일 2시간 5분'),
    ],
)
def test_how_long_reads(minutes: int, text: str):
    assert time_words.duration_text(minutes) == text


@pytest.mark.parametrize(
    ('part', 'word'),
    [
        (TimeOfDay.DAWN, '새벽'),
        (TimeOfDay.MORNING, '아침'),
        (TimeOfDay.DAY, '낮'),
        (TimeOfDay.EVENING, '저녁'),
        (TimeOfDay.NIGHT, '밤'),
    ],
)
def test_every_part_of_the_day_has_a_word(part: TimeOfDay, word: str):
    assert time_words.TIME_OF_DAY_WORDS[part] == word
