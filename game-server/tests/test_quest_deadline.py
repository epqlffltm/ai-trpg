# game-server/tests/test_quest_deadline.py

"""
퀘스트의 기한(달력 2단계, 판 형식 27)을 검증한다.

넷을 본다.
  - 판: 퀘스트 규칙에 드러난 때부터 세는 기한(time_limit_minutes)을 적는다. 1분부터 한 해까지다.
    옛 판은 기한 없이 읽는다.
  - 정하기: 처음부터 진행 중인 것은 테이블이 시작하는 시각부터, 숨겼다가 드러낸 것은 드러낸 라운드가 열린 시각부터 센다.
    숨긴 것과 숨김에서 바로 끝낸 것에는 기한이 없다.
  - 실패: 기한이 지난 뒤 처음 열린 라운드가 닫힐 때까지 진행 중이면 서버가 실패로 바꾼다.
    기한이 장면 안에서 끝난 라운드에는 바꾸지 않는다. 방장이 그 장면의 서술을 보고 결과를 정할 틈이다.
    이미 끝낸 것과 기한이 없는 것은 건드리지 않는다.
  - 보이기: 응답, 이벤트, 서술자에게 간다. 서버가 바꾼 것은 누가 했는지가 비어 있고 까닭이 적힌다.
"""

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import QUEST_MAX_TIME_LIMIT_MINUTES
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_26
from app.rounds.narrator import QuestNote
from app.tables import quests
from app.tables.models import QuestStatus, TableQuest
from tests import test_table_quests as quest_tables
from tests.narration_model import with_model
from tests.sheets import SHEET
from tests.test_map_actions import play
from tests.test_table_items import (
    FRIEND,
    ME,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    events_of,
    held,
    post,
    read_table,
    table_url,
)
from tests.test_table_quests import change, quests_in
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

# 퀘스트 테스트의 픽스처를 그대로 쓴다. 방장(기사), 함께 앉는 사람(약사), 사건 셋과 물건 둘이 든 로어북
me = quest_tables.me
friend = quest_tables.friend
lore = quest_tables.lore

HOUR = 60
# 판의 시계는 기본값이다. 1일째 8시에 시작하고 라운드 하나에 10분이 흐른다
EIGHT = 8 * HOUR


def clock_at(minutes: int) -> dict:
    """게임 안의 시각을 응답의 모양으로(1일째 안의 시각만)."""
    hour, minute = divmod(minutes, HOUR)
    time_of_day = 'morning' if 7 <= hour < 11 else 'day'
    return {'day': 1, 'hour': hour, 'minute': minute, 'time_of_day': time_of_day}


async def open_with_deadlines(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """
    둘이 앉은 테이블. 시작하지 않았다.

    판: 왕녀 구출은 처음부터 진행 중이고 기한이 20분이다. 성공하면 물약 둘을 준다.
    배신자는 숨긴 채로 시작하고 드러나면 기한이 한 시간이다. 광산의 비밀은 규칙이 없다(숨김, 기한 없음).
    """
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '왕녀의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'lorebook_ids': [lore['lorebook']['id']],
        'quests': [
            {
                'entry_id': lore['rescue']['id'],
                'start': 'active',
                'reward': [{'entry_id': lore['potion']['id'], 'count': 2}],
                'time_limit_minutes': 20,
            },
            {'entry_id': lore['traitor']['id'], 'time_limit_minutes': HOUR},
        ],
    }
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2)
    joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    assert joined.status_code == status.HTTP_200_OK, joined.text
    await client.put(table_url(table, '/character'), json={'name': '기사'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '약사'}, headers=friend)
    return table


async def start_with_deadlines(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """둘이 앉아 시작한 테이블."""
    table = await open_with_deadlines(client, me, friend, lore)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def step(client: AsyncClient, me: dict, table: dict, minutes: int) -> None:
    """방장이 다음 라운드가 열릴 때 흐를 시간을 정한다."""
    response = await client.put(table_url(table, '/clock/step'), json={'minutes': minutes}, headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text


def due_of(table: dict, name: str) -> dict | None:
    """응답에서 그 퀘스트의 기한."""
    return next(quest['due_at'] for quest in table['quests'] if quest['name'] == name)


# --- 판 ---


@pytest.mark.parametrize('minutes', [0, -1, QUEST_MAX_TIME_LIMIT_MINUTES + 1, '사흘'])
async def test_rejects_a_bad_time_limit(client: AsyncClient, me: dict, lore: dict, minutes):
    body = {'title': '기한', 'quests': [{'entry_id': lore['rescue']['id'], 'time_limit_minutes': minutes}]}

    response = await client.post(SCENARIOS_URL, json=with_model(body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_an_old_version_reads_every_quest_as_having_no_time_limit():
    old = {'format': 26, 'quests': [{'entry_id': 'a', 'start': 'active', 'reward': []}]}

    upgraded = upgrade_from_26(old)

    assert upgraded['quests'] == [{'entry_id': 'a', 'start': 'active', 'reward': [], 'time_limit_minutes': None}]
    assert upgraded['format'] == 27
    assert 'time_limit_minutes' not in old['quests'][0]
    assert UPGRADES[26] is upgrade_from_26


# --- 정하기 ---


async def test_an_active_quest_counts_from_the_start(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_with_deadlines(client, me, friend, lore)

    # 8시에 시작해 20분 뒤. 숨긴 것과 규칙이 없는 것에는 기한이 없다
    assert due_of(table, '왕녀 구출') == clock_at(EIGHT + 20)
    assert due_of(table, '배신자') is None
    assert due_of(table, '광산의 비밀') is None


async def test_a_revealed_quest_counts_from_the_round_it_was_revealed(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_with_deadlines(client, me, friend, lore)
    await play(client, me, friend, table, narrated)

    # 둘째 라운드는 8시 10분에 열렸다. 그때부터 한 시간
    response = await change(client, me, table, lore['traitor'], 'active')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert due_of(await read_table(client, friend, table), '배신자') == clock_at(EIGHT + 10 + HOUR)
    [event] = await events_of(client, friend, table, 'quest_changed')
    assert event['payload']['due_at'] == clock_at(EIGHT + 10 + HOUR)
    assert event['payload']['reason'] is None


async def test_a_quest_finished_while_hidden_has_no_time_limit(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_with_deadlines(client, me, friend, lore)

    response = await change(client, me, table, lore['traitor'], 'failed')

    assert due_of(response.json(), '배신자') is None


# --- 실패 ---


async def test_an_overdue_quest_fails_one_round_after_its_deadline(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_with_deadlines(client, me, friend, lore)
    await step(client, me, table, HOUR)

    # 8시의 장면이 한 시간 이어지는 동안 기한(8시 20분)이 지났다. 그 결과는 서술이 끝나야 보인다
    await play(client, me, friend, table, narrated)
    assert ('왕녀 구출', 'active') in quests_in(await read_table(client, friend, table))

    # 방장이 9시에 열린 라운드에서도 정하지 않았다. 그 라운드가 닫히면 실패다
    await play(client, me, friend, table, narrated)

    seen = await read_table(client, friend, table)
    assert ('왕녀 구출', 'failed') in quests_in(seen)
    assert held(seen, ME) == held(seen, FRIEND) == []
    [event] = await events_of(client, friend, table, 'quest_changed')
    assert event['actor_id'] is None
    assert event['payload'] == {
        'entry_id': lore['rescue']['id'],
        'name': '왕녀 구출',
        'previous': 'active',
        'status': 'failed',
        'rewards': [],
        'due_at': clock_at(EIGHT + 20),
        'reason': 'deadline',
    }


async def test_the_failure_is_in_the_closing_group(client: AsyncClient, me: dict, friend: dict, lore: dict, narrated):
    table = await start_with_deadlines(client, me, friend, lore)
    await step(client, me, table, HOUR)
    await play(client, me, friend, table, narrated)
    await play(client, me, friend, table, narrated)

    [failed] = await events_of(client, me, table, 'quest_changed')
    closed = (await events_of(client, me, table, 'round_closed'))[-1]

    # 닫힘의 바로 앞에 같은 묶음으로 적힌다
    assert failed['action_group_id'] == closed['action_group_id']
    assert failed['sequence'] < closed['sequence']


async def test_a_quest_the_host_finished_in_time_is_left_alone(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_with_deadlines(client, me, friend, lore)
    await step(client, me, table, HOUR)
    await play(client, me, friend, table, narrated)

    # 기한이 지났어도 방장이 먼저 실패로 끝냈다. 끝난 것은 기한이 다시 바꾸지 않는다
    await change(client, me, table, lore['rescue'], 'failed')
    await play(client, me, friend, table, narrated)

    seen = await read_table(client, friend, table)
    assert ('왕녀 구출', 'failed') in quests_in(seen)
    assert len(await events_of(client, me, table, 'quest_changed')) == 1


async def test_a_quest_without_a_time_limit_never_fails(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_with_deadlines(client, me, friend, lore)
    await change(client, me, table, lore['mine'], 'active')
    await step(client, me, table, 7 * 24 * HOUR)

    await play(client, me, friend, table, narrated)
    await play(client, me, friend, table, narrated)

    assert ('광산의 비밀', 'active') in quests_in(await read_table(client, friend, table))


async def test_the_narrator_hears_that_the_quest_failed(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start_with_deadlines(client, me, friend, lore)
    await step(client, me, table, HOUR)

    await play(client, me, friend, table, narrated)
    await play(client, me, friend, table, narrated)

    first, second = narrator.requests
    assert QuestNote(name='왕녀 구출', status='active') in first.quests
    assert QuestNote(name='왕녀 구출', status='failed') in second.quests


# --- 작은 함수들 ---


def row(status: QuestStatus, due_at: int | None) -> TableQuest:
    return TableQuest(status=status, due_at=due_at)


@pytest.mark.parametrize(
    ('quest', 'overdue'),
    [
        # 기한이 라운드가 열린 때와 같거나 앞이면 넘겼다
        (row(QuestStatus.ACTIVE, 500), True),
        (row(QuestStatus.ACTIVE, 499), True),
        # 기한이 장면 안에서 끝난다. 이 라운드에는 아직이다
        (row(QuestStatus.ACTIVE, 501), False),
        # 기한이 없거나, 숨겼거나, 이미 끝났다
        (row(QuestStatus.ACTIVE, None), False),
        (row(QuestStatus.HIDDEN, 100), False),
        (row(QuestStatus.SUCCEEDED, 100), False),
        (row(QuestStatus.FAILED, 100), False),
    ],
)
def test_which_quests_are_overdue(quest: TableQuest, overdue: bool):
    assert quests.is_overdue(quest, round_opened_at=500) is overdue


async def test_a_negative_due_time_is_refused_by_the_database(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    await start_with_deadlines(client, me, friend, lore)

    with pytest.raises(IntegrityError):
        await session.execute(text('UPDATE table_quests SET due_at = -1'))
    await session.rollback()
