# game-server/tests/test_table_quests.py

"""
테이블의 퀘스트.

다섯을 본다.
  - 시작: 판의 사건마다 퀘스트가 생긴다. 처음 상태는 판의 퀘스트 규칙의 것이고, 규칙이 없으면 숨김이다.
  - 보이기: 숨긴 것은 방장만 본다. 사건의 글(로어북)은 아무에게도 나가지 않는다.
  - 방장이 바꾸기: 진행 중에, 판의 퀘스트만, 정한 길로만. 끝난 것은 되돌리지 않는다. 이벤트로 남는다.
  - 보상: 성공하면 살아 있는 캐릭터마다 받는다. 한 가지 99 개에 닿으면 거기까지만 받는다. 두 번 주지 않는다.
  - 서술: 서술을 맡길 때 퀘스트 전부가 이름과 상태로 서술자에게 간다. 닫기 시작할 때 굳히지 않는다.
"""

import asyncio
import uuid
from dataclasses import replace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds import prompt, service
from app.rounds.narrator import NarrationRequest, QuestNote, WhisperNote
from app.tables import items
from app.tables.errors import TableConflictError
from app.tables.models import QuestStatus, TableItem, TableSheet
from app.tables.quests import require_changeable
from tests.sheets import SHEET
from tests.test_round_closing import HeldJobs, started_at
from tests.test_table_items import (
    FRIEND,
    LOREBOOKS_URL,
    ME,
    NO_SUCH_ID,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    bearer,
    events_of,
    give,
    held,
    kill,
    post,
    read_table,
    table_url,
)
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

# 사건 항목의 글. AI 가 읽는 설정이다. 플레이어에게도 방장에게도 나가지 않는지 본다
TRAITOR_SECRET = '집사가 배신자다.'


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    """방장의 머리말. 직접 만든 캐릭터(기사)를 한다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    """함께 앉는 사람의 머리말. 직접 만든 캐릭터(약사)를 한다."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """사건 셋(왕녀 구출, 광산의 비밀, 배신자), 물건 둘(치유 물약, 밧줄), 인물 하나가 든 로어북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='모험의 사건들')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str, content: str = '') -> dict:
        return await post(client, url, me, name=name, keywords=[], content=content or f'{name}의 설명', kind=kind)

    return {
        'lorebook': lorebook,
        'rescue': await entry('왕녀 구출', 'event'),
        'mine': await entry('광산의 비밀', 'event'),
        'traitor': await entry('배신자', 'event', TRAITOR_SECRET),
        'potion': await entry('치유 물약', 'item'),
        'rope': await entry('밧줄', 'item'),
        'lady': await entry('악역영애', 'person'),
    }


async def open_duo(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """
    둘이 앉은 테이블. 시작하지 않았다.

    판: 왕녀 구출은 처음부터 진행 중이고 성공하면 물약 둘과 밧줄 하나를 준다.
    광산의 비밀은 규칙이 없다(숨김, 보상 없음). 배신자는 숨긴 채로 시작하고 성공하면 물약 하나를 준다.
    """
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    reward = [{'entry_id': lore['potion']['id'], 'count': 2}, {'entry_id': lore['rope']['id'], 'count': 1}]
    body = {
        'title': '왕녀의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'lorebook_ids': [lore['lorebook']['id']],
        'quests': [
            {'entry_id': lore['rescue']['id'], 'start': 'active', 'reward': reward},
            {'entry_id': lore['traitor']['id'], 'reward': [{'entry_id': lore['potion']['id'], 'count': 1}]},
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


async def start_duo(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """둘이 앉아 시작한 테이블."""
    table = await open_duo(client, me, friend, lore)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def change(client: AsyncClient, headers: dict, table: dict, entry: dict, to: str):
    """퀘스트의 상태를 바꾸는 요청. 응답을 그대로 돌려준다."""
    return await client.put(table_url(table, f'/quests/{entry["id"]}'), json={'status': to}, headers=headers)


def quests_in(table: dict) -> list[tuple[str, str]]:
    """응답의 퀘스트들을 (이름, 상태)로."""
    return [(quest['name'], quest['status']) for quest in table['quests']]


# --- 시작과 보이기 ---


async def test_quests_appear_when_the_table_starts(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await open_duo(client, me, friend, lore)
    assert (await read_table(client, me, table))['quests'] == []

    started = await start_duo_from(client, me, table)

    # 판의 순서(로어북의 항목 순서)다. 규칙이 없는 광산의 비밀은 숨긴 채로 시작한다
    assert quests_in(started) == [('왕녀 구출', 'active'), ('광산의 비밀', 'hidden'), ('배신자', 'hidden')]
    assert started['quests'][0]['entry_id'] == lore['rescue']['id']


async def start_duo_from(client: AsyncClient, me: dict, table: dict) -> dict:
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def test_hidden_quests_are_shown_only_to_the_host(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    seen = await read_table(client, friend, table)

    # 숨긴 것이 있다는 것조차 알리지 않는다
    assert quests_in(seen) == [('왕녀 구출', 'active')]


async def test_the_text_of_an_event_never_leaves(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)
    await change(client, me, table, lore['traitor'], 'succeeded')

    for headers in (me, friend):
        detail = await client.get(table_url(table), headers=headers)
        stream = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=headers)
        assert TRAITOR_SECRET not in detail.text
        assert TRAITOR_SECRET not in stream.text


# --- 방장이 바꾸기 ---


async def test_revealing_a_quest_shows_it_to_everyone(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await change(client, me, table, lore['mine'], 'active')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert quests_in(await read_table(client, friend, table)) == [('왕녀 구출', 'active'), ('광산의 비밀', 'active')]
    [event] = await events_of(client, friend, table, 'quest_changed')
    assert event['payload'] == {
        'entry_id': lore['mine']['id'],
        'name': '광산의 비밀',
        'previous': 'hidden',
        'status': 'active',
        'rewards': [],
    }


async def test_a_hidden_quest_can_be_finished_at_once(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await change(client, me, table, lore['traitor'], 'succeeded')

    # 몰래 이룬 일이다. 끝난 것은 모두에게 보이고 보상도 받는다
    assert response.status_code == status.HTTP_200_OK, response.text
    assert ('배신자', 'succeeded') in quests_in(await read_table(client, friend, table))
    assert held(response.json(), FRIEND) == [('치유 물약', 1)]


async def test_a_quest_can_fail(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await change(client, me, table, lore['rescue'], 'failed')

    # 실패하면 보상이 없다
    assert response.status_code == status.HTTP_200_OK, response.text
    assert quests_in(response.json())[0] == ('왕녀 구출', 'failed')
    assert held(response.json(), ME) == held(response.json(), FRIEND) == []
    [event] = await events_of(client, friend, table, 'quest_changed')
    assert (event['payload']['previous'], event['payload']['status'], event['payload']['rewards']) == (
        'active',
        'failed',
        [],
    )


@pytest.mark.parametrize(
    ('first', 'second', 'reason'),
    [
        ('succeeded', 'failed', 'quest_finished'),
        ('failed', 'succeeded', 'quest_finished'),
        ('failed', 'active', 'quest_finished'),
        ('active', 'active', 'quest_already_active'),
    ],
)
async def test_some_changes_are_refused(
    client: AsyncClient, me: dict, friend: dict, lore: dict, first: str, second: str, reason: str
):
    table = await start_duo(client, me, friend, lore)
    await change(client, me, table, lore['mine'], first)

    response = await change(client, me, table, lore['mine'], second)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == reason
    assert len(await events_of(client, me, table, 'quest_changed')) == 1


@pytest.mark.parametrize('to', ['hidden', 'done', ''])
async def test_a_quest_cannot_be_hidden_again_or_given_a_made_up_status(
    client: AsyncClient, me: dict, friend: dict, lore: dict, to: str
):
    table = await start_duo(client, me, friend, lore)

    response = await change(client, me, table, lore['rescue'], to)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize('what', ['potion', 'lady', 'nothing'])
async def test_only_quests_of_the_table_can_be_changed(
    client: AsyncClient, me: dict, friend: dict, lore: dict, what: str
):
    table = await start_duo(client, me, friend, lore)
    entry = {'id': NO_SUCH_ID} if what == 'nothing' else lore[what]

    response = await change(client, me, table, entry, 'active')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_only_the_host_changes_quests(client: AsyncClient, me: dict, friend: dict, stranger: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    by_friend = await change(client, friend, table, lore['mine'], 'active')
    by_stranger = await change(client, stranger, table, lore['mine'], 'active')

    assert by_friend.status_code == status.HTTP_403_FORBIDDEN
    assert by_stranger.status_code == status.HTTP_404_NOT_FOUND
    assert await events_of(client, me, table, 'quest_changed') == []


async def test_quests_change_only_while_playing(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await open_duo(client, me, friend, lore)
    before = await change(client, me, table, lore['mine'], 'active')
    await start_duo_from(client, me, table)
    await client.post(table_url(table, '/end'), headers=me)
    after = await change(client, me, table, lore['mine'], 'active')

    assert (before.status_code, after.status_code) == (status.HTTP_409_CONFLICT, status.HTTP_409_CONFLICT)
    assert before.json()['reason'] == after.json()['reason'] == 'not_playing'


async def test_a_table_started_before_quests_existed_has_none_to_change(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    # 퀘스트가 생기기 전에 시작한 테이블에는 퀘스트의 행이 없다
    await session.execute(text('DELETE FROM table_quests WHERE table_id = :table_id'), {'table_id': table['id']})
    await session.commit()

    response = await change(client, me, table, lore['mine'], 'active')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await read_table(client, me, table))['quests'] == []


# --- 보상 ---


async def test_every_living_character_is_rewarded(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await change(client, me, table, lore['rescue'], 'succeeded')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert held(response.json(), ME) == held(response.json(), FRIEND) == [('치유 물약', 2), ('밧줄', 1)]
    [event] = await events_of(client, friend, table, 'quest_changed')
    gained = [
        {'entry_id': lore['potion']['id'], 'name': '치유 물약', 'count': 2, 'total': 2, 'capped': False},
        {'entry_id': lore['rope']['id'], 'name': '밧줄', 'count': 1, 'total': 1, 'capped': False},
    ]
    assert event['payload']['rewards'] == [
        {'user_id': str(ME), 'character_name': '기사', 'items': gained},
        {'user_id': str(FRIEND), 'character_name': '약사', 'items': gained},
    ]


async def test_a_dead_character_gets_no_reward(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await kill(session, FRIEND)

    response = await change(client, me, table, lore['rescue'], 'succeeded')

    assert held(response.json(), FRIEND) == []
    [event] = await events_of(client, me, table, 'quest_changed')
    assert [reward['user_id'] for reward in event['payload']['rewards']] == [str(ME)]


async def test_a_full_stack_takes_only_what_fits(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)
    await give(client, me, table, ME, lore['potion'], 98)

    response = await change(client, me, table, lore['rescue'], 'succeeded')

    # 가득 찬 사람은 거기까지만 받는다. 다른 사람의 보상은 그대로다
    assert response.status_code == status.HTTP_200_OK, response.text
    assert held(response.json(), ME) == [('치유 물약', 99), ('밧줄', 1)]
    assert held(response.json(), FRIEND) == [('치유 물약', 2), ('밧줄', 1)]
    [event] = await events_of(client, me, table, 'quest_changed')
    mine = event['payload']['rewards'][0]['items'][0]
    assert (mine['count'], mine['total'], mine['capped']) == (1, 99, True)


async def test_a_quest_without_a_reward_rewards_nobody(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await change(client, me, table, lore['mine'], 'succeeded')

    assert held(response.json(), ME) == []
    [event] = await events_of(client, me, table, 'quest_changed')
    assert event['payload']['rewards'] == []


async def test_a_quest_succeeding_twice_at_once_rewards_once(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    # 잠그지 않으면 둘 다 "진행 중"을 보고 보상을 두 번 준다
    first, second = await asyncio.gather(
        change(client, me, table, lore['rescue'], 'succeeded'), change(client, me, table, lore['rescue'], 'succeeded')
    )

    assert sorted([first.status_code, second.status_code]) == [status.HTTP_200_OK, status.HTTP_409_CONFLICT]
    assert held(await read_table(client, me, table), FRIEND) == [('치유 물약', 2), ('밧줄', 1)]


# --- 규칙과 DB ---


@pytest.mark.parametrize(
    ('current', 'to'),
    [
        (QuestStatus.HIDDEN, QuestStatus.ACTIVE),
        (QuestStatus.HIDDEN, QuestStatus.SUCCEEDED),
        (QuestStatus.HIDDEN, QuestStatus.FAILED),
        (QuestStatus.ACTIVE, QuestStatus.SUCCEEDED),
        (QuestStatus.ACTIVE, QuestStatus.FAILED),
    ],
)
def test_the_allowed_changes(current: QuestStatus, to: QuestStatus):
    require_changeable(current, to)


def test_adding_up_to_the_cap_gives_what_fits():
    entry_id = uuid.uuid4()
    sheet = TableSheet(items=[TableItem(entry_id=entry_id, count=97)])

    assert items.add_up_to(uuid.uuid4(), sheet, entry_id, 5) == 2
    assert items.count_of(sheet, entry_id) == 99
    # 가득 찼으면 하나도 주지 않는다
    other = uuid.uuid4()
    assert items.add_up_to(uuid.uuid4(), sheet, entry_id, 1) == 0
    assert items.add_up_to(uuid.uuid4(), sheet, other, 3) == 3
    assert [(item.entry_id, item.count) for item in sheet.items] == [(entry_id, 99), (other, 3)]


def test_a_finished_quest_stays_finished():
    with pytest.raises(TableConflictError):
        require_changeable(QuestStatus.SUCCEEDED, QuestStatus.SUCCEEDED)


async def test_the_database_refuses_a_made_up_status(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)

    with pytest.raises(IntegrityError):
        await session.execute(
            text("UPDATE table_quests SET status = 'done' WHERE table_id = :table_id"), {'table_id': table['id']}
        )


# --- 서술 ---


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


async def declare_both(client: AsyncClient, me: dict, friend: dict, table: dict) -> None:
    """둘 다 선언한다. 다 내면 라운드가 닫기 시작한다."""
    for headers in (me, friend):
        url = table_url(table, '/rounds/current/declaration')
        declared = await client.put(url, json={'content': '주위를 살핀다.'}, headers=headers)
        assert declared.status_code == status.HTTP_200_OK, declared.text


async def test_the_narrator_gets_every_quest_with_its_status(
    client: AsyncClient, me: dict, friend: dict, lore: dict, recording: RecordingNarrator, narrated
):
    table = await start_duo(client, me, friend, lore)
    await change(client, me, table, lore['rescue'], 'succeeded')

    await declare_both(client, me, friend, table)
    await narrated()

    # 판의 순서다. 끝난 것도, 숨긴 것도 간다. 숨긴 것을 드러내지 않는 것은 다루는 법이 맡는다
    (request,) = recording.requests
    assert request.quests == [
        QuestNote(name='왕녀 구출', status='succeeded'),
        QuestNote(name='광산의 비밀', status='hidden'),
        QuestNote(name='배신자', status='hidden'),
    ]


async def test_a_quest_changed_after_closing_reaches_the_narration(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, session: AsyncSession, held_jobs: HeldJobs
):
    table = await start_duo(client, me, friend, lore)
    await declare_both(client, me, friend, table)
    started = await started_at(app, table)

    # 결정적인 라운드가 닫힌 뒤 방장이 성공을 적었다. 그 라운드의 서술이 성공을 그릴 수 있어야 한다
    await change(client, me, table, lore['rescue'], 'succeeded')
    request = await service.load_closing_request(session, uuid.UUID(table['id']), 1, started)

    assert request.quests[0] == QuestNote(name='왕녀 구출', status='succeeded')


def make_request(quests: list[QuestNote], whispers: list[WhisperNote] | None = None) -> NarrationRequest:
    """퀘스트(와 쪽지)만 정한 서술 요청."""
    request = NarrationRequest(round_number=2, scene='성문 앞.', moves=[])
    return replace(request, quests=quests, whispers=whispers or [])


def test_the_prompt_lists_the_quests_with_how_to_treat_them():
    quests = [
        QuestNote('왕녀 구출', 'active'),
        QuestNote('광산의 비밀', 'hidden'),
        QuestNote('배신자', 'succeeded'),
        QuestNote('용의 둥지', 'failed'),
    ]

    text = prompt.round_text(make_request(quests, [WhisperNote('엘프', '영애', '쉿')]))

    assert prompt.QUEST_TITLE in text
    assert prompt.QUEST_NOTE in text
    assert '- 왕녀 구출: 진행 중' in text
    assert '- 광산의 비밀: 숨김(플레이어는 모름)' in text
    assert '- 배신자: 성공' in text
    assert '- 용의 둥지: 실패' in text
    # 쪽지 뒤, 이번 라운드의 차례 앞이다
    assert text.index(prompt.WHISPER_TITLE) < text.index(prompt.QUEST_TITLE) < text.index('[2 라운드에 한 일과 결과]')


def test_no_quests_no_section():
    assert prompt.QUEST_TITLE not in prompt.round_text(make_request([]))
