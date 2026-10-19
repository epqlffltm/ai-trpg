# trpg-server/tests/test_quest_pace.py

"""
서술이 퀘스트의 기한을 아는 것(#268)을 검증한다.

판과 픽스처는 tests/test_quest_deadline.py 의 것이다. 왕녀 구출은 처음부터 진행 중이고 기한이 20분이다(8시 20분).
판의 시계는 1일째 8시에 시작하고 라운드 하나에 10분이 흐른다. 배신자와 광산의 비밀은 숨긴 채로 시작한다.

보는 것.
  - 진행 중이고 기한이 있는 퀘스트에 남은 시간의 감각이 붙는다. 이번 장면이 끝나는 시각에서 잰다.
    절반보다 많으면 넉넉함, 절반 이하면 빠듯함, 장면이 끝날 때 지나면 다 됨(다음 라운드가 마지막)이다. 숫자는 없다.
  - 이번 라운드에 기한을 넘겨 실패한 퀘스트는 그것이 붙는다. 그 다음 라운드부터는 붙지 않는다.
    방장이 실패로 바꾼 것은 기한을 넘긴 것이 아니다. 라운드에 적어 두어 서술을 다시 맡겨도 같다.
  - 숨긴 퀘스트와 기한이 없는 퀘스트에는 아무것도 붙지 않는다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds import prompt
from app.rounds.models import Round
from app.rounds.narration_request import Pace, pace_of, scene_end_of
from app.rounds.narrator import QuestNote
from tests import test_table_quests as quest_tables
from tests.test_map_actions import play
from tests.test_quest_deadline import HOUR, start_with_deadlines, step
from tests.test_table_quests import change
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = quest_tables.me
friend = quest_tables.friend
lore = quest_tables.lore


@pytest.fixture
def narrator(app: FastAPI) -> RecordingNarrator:
    recording = RecordingNarrator()
    app.state.narrator = recording
    return recording


def rescue(request) -> QuestNote:
    """서술 요청에서 왕녀 구출."""
    return next(quest for quest in request.quests if quest.name == '왕녀 구출')


async def expired_in(session: AsyncSession, table: dict, number: int) -> list[str]:
    query = select(Round.expired_quests).where(Round.table_id == uuid.UUID(table['id']), Round.number == number)
    return await session.scalar(query.execution_options(populate_existing=True))


# --- 서술 요청 ---


async def test_the_narrator_hears_how_tight_the_deadline_is(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrator: RecordingNarrator, narrated
):
    table = await start_with_deadlines(client, me, friend, lore)

    await play(client, me, friend, table, narrated)

    (request,) = narrator.requests
    # 장면이 끝나는 8시 10분에 10분이 남는다. 기한(20분)의 절반 이하다
    assert request.quests == [
        QuestNote(name='왕녀 구출', status='active', pace=Pace.TIGHT),
        QuestNote(name='광산의 비밀', status='hidden'),
        QuestNote(name='배신자', status='hidden'),
    ]


async def test_only_the_round_that_missed_the_deadline_says_so(
    client: AsyncClient,
    me: dict,
    friend: dict,
    lore: dict,
    narrator: RecordingNarrator,
    session: AsyncSession,
    narrated,
):
    table = await start_with_deadlines(client, me, friend, lore)
    await step(client, me, table, HOUR)

    for _ in range(3):
        await play(client, me, friend, table, narrated)

    first, second, third = (rescue(request) for request in narrator.requests)
    assert (first.pace, first.missed_deadline) == (Pace.LAST, False)
    assert (second.status, second.pace, second.missed_deadline) == ('failed', None, True)
    assert (third.status, third.missed_deadline) == ('failed', False)
    assert await expired_in(session, table, 2) == [lore['rescue']['id']]
    assert await expired_in(session, table, 3) == []


async def test_a_quest_failed_by_the_host_did_not_miss_its_deadline(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrator: RecordingNarrator, narrated
):
    table = await start_with_deadlines(client, me, friend, lore)
    await change(client, me, table, lore['rescue'], 'failed')

    await play(client, me, friend, table, narrated)

    assert rescue(narrator.requests[0]) == QuestNote(name='왕녀 구출', status='failed')


async def test_the_prompt_shows_the_feeling_but_no_numbers(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrator: RecordingNarrator, narrated
):
    table = await start_with_deadlines(client, me, friend, lore)
    await play(client, me, friend, table, narrated)

    text = prompt.round_text(narrator.requests[0])

    assert '- 왕녀 구출: 진행 중(기한 빠듯함)' in text
    assert '- 배신자: 숨김(플레이어는 모름)\n' in text


# --- DB 를 쓰지 않는 작은 함수들 ---


@pytest.mark.parametrize(
    ('due_at', 'scene_end', 'expected'),
    [
        # 기한 60분. 장면이 끝날 때 31분 남으면 넉넉함, 30분이면 빠듯함
        (131, 100, Pace.AMPLE),
        (130, 100, Pace.TIGHT),
        (101, 100, Pace.TIGHT),
        # 장면이 끝날 때 기한이 닿았거나 지났다
        (100, 100, Pace.LAST),
        (90, 100, Pace.LAST),
    ],
)
def test_the_pace_is_measured_at_the_end_of_the_scene(due_at: int, scene_end: int, expected: str):
    assert pace_of(60, due_at, scene_end) == expected


def test_without_a_deadline_there_is_no_pace():
    assert (pace_of(None, 100, 50), pace_of(60, None, 50)) == (None, None)


def test_without_a_clock_there_is_no_scene_end():
    assert scene_end_of(SimpleNamespace(clock=None)) is None


@pytest.mark.parametrize(
    ('quest', 'line'),
    [
        (QuestNote('왕녀 구출', 'active'), '- 왕녀 구출: 진행 중'),
        (QuestNote('왕녀 구출', 'active', pace=Pace.AMPLE), '- 왕녀 구출: 진행 중(기한 넉넉함)'),
        (QuestNote('왕녀 구출', 'active', pace=Pace.LAST), '- 왕녀 구출: 진행 중(기한이 다 됨(다음 라운드가 마지막))'),
        (QuestNote('왕녀 구출', 'failed', missed_deadline=True), '- 왕녀 구출: 실패(이번 라운드에 기한을 넘김)'),
        (QuestNote('왕녀 구출', 'failed'), '- 왕녀 구출: 실패'),
    ],
)
def test_the_quest_line(quest: QuestNote, line: str):
    assert prompt.quest_line(quest) == line


def test_the_note_forbids_made_up_numbers():
    assert '숫자로 지어내지 마라' in prompt.QUEST_NOTE


def test_a_deadline_that_is_up_or_missed_is_repeated_before_the_request():
    quests = [
        QuestNote('왕녀 구출', 'active', pace=Pace.LAST),
        QuestNote('배달', 'active', pace=Pace.TIGHT),
        QuestNote('광산의 비밀', 'failed', missed_deadline=True),
        QuestNote('배신자', 'hidden'),
    ]

    assert prompt.deadline_reminders(quests) == [
        "'왕녀 구출' 의 기한이 다 됐다. 남은 기회는 다음 라운드 하나뿐이다. 시간이 없다는 긴장을 장면에 드러내라.",
        "'광산의 비밀' 은(는) 이번 라운드에 기한을 넘겨 실패했다. 때를 놓쳐 일이 틀어진 것을 장면에 드러내라.",
    ]


async def test_the_reminder_sits_just_before_the_request(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrator: RecordingNarrator, narrated
):
    table = await start_with_deadlines(client, me, friend, lore)
    await step(client, me, table, HOUR)
    await play(client, me, friend, table, narrated)

    lines = prompt.round_text(narrator.requests[0]).splitlines()

    assert lines[-1] == prompt.CLOSING_REQUEST
    assert lines.index(prompt.THIS_ROUND_ONLY) + 1 == lines.index(prompt.QUEST_LAST_REMINDER.format(name='왕녀 구출'))


async def test_a_tight_deadline_is_not_repeated(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrator: RecordingNarrator, narrated
):
    table = await start_with_deadlines(client, me, friend, lore)
    await play(client, me, friend, table, narrated)

    text = prompt.round_text(narrator.requests[0])

    assert '기한이 다 됐다' not in text
    assert '기한을 넘겨 실패했다' not in text
