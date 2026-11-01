# trpg-server/tests/test_chapter_locks.py

"""
장이 여는 것(#481 ②-b, app/tables/chapters.py 의 locked_ids)을 검증한다.
지금 장 뒤의 장이 여는 장소와 퀘스트는 닫혀 있다.

맵과 픽스처는 tests/test_happenings.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 성문(시작)-광장 큰길,
광장→지하실 숨긴 길(지혜 어려움 20 으로 찾는다), 성문-숲 안개 길, 오두막-숲 안개 길, 탑은 명소다.
장은 둘이다. 도착(처음)과 둘째 장(광장에 닿으면). 둘째 장이 무엇을 여는지는 시험마다 다르다.

보는 것.
  - 장소: 닫힌 장소는 지도에 없고, 그곳으로 이어진 길도 모른다. 그곳으로 가는 선언은 받지 않는다(422).
    그곳으로 이어진 숨긴 길은 찾지 못한다(굴리지 않는다). 장이 열리면 그때부터 보이고 간다.
  - 사건: 캐릭터를 닫힌 장소로 옮기는 사건은 조건이 채워져도 기다린다. 장이 열린 뒤에 일어난다.
  - 퀘스트: 닫힌 퀘스트는 진행 중으로 시작해도 숨긴 채이고 조건이 채워져도 이루지 않는다.
    장이 열릴 때 드러나고(quest_changed, chapter_opened) 기한도 그때부터 센다. 이루는 것은 다음 라운드다.
  - 서술: 닫힌 퀘스트는 서술자에게 가지 않는다. 닫힌 장소와 퀘스트의 로어북 항목은 검색의 후보에 들지 않는다.
  - 장이 없는 판과 장이 생기기 전에 시작한 테이블은 아무것도 막지 않는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.lore.retrieval import load_candidates
from tests import test_happenings as happening_tests
from tests.test_happenings import reach, start, trap
from tests.test_map_actions import SEARCHING, declare, going, load_dice, outcome_of, play
from tests.test_table_items import ME, events_of, read_table
from tests.test_table_map import known_places, known_routes, place_of, put_at
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = happening_tests.me
friend = happening_tests.friend
lore = happening_tests.lore
more = happening_tests.more


def chapters_opening(more: dict, when: list[dict] | None = None, **opens: list[str]) -> list[dict]:
    """도착(처음)과, 광장에 닿으면(when 을 주면 그것으로) 넘어오는 둘째 장. opens 는 places=, quests= 의 이름표다."""
    opened = {kind: [more[key]['id'] for key in keys] for kind, keys in opens.items()}
    second = {'id': 'later', 'name': '다음', 'when': when or [reach(more['square'])], 'opens': opened}
    return [{'id': 'arrival', 'name': '도착'}, second]


def never(more: dict) -> list[dict]:
    """채워지지 않는 조건. 치유 물약 99 개를 지닌다."""
    return [{'kind': 'hold_item', 'target': more['potion']['id'], 'count': 99}]


def rescue(more: dict, **fields) -> dict:
    """진행 중으로 시작하고 광장에 닿으면 이루는 왕녀 구출."""
    return {
        'entry_id': more['rescue']['id'],
        'start': 'active',
        'conditions': [reach(more['square'])],
        **fields,
    }


def quest_status(table: dict, name: str) -> str | None:
    """보이는 퀘스트의 상태. 보이지 않으면 None 이다."""
    return next((quest['status'] for quest in table['quests'] if quest['name'] == name), None)


# --- 장소 ---


async def test_a_locked_place_is_off_the_map_until_its_chapter(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    # 탑은 명소라 길을 몰라도 지도에 있다. 닫혀 있으면 명소도 없다
    chapters = chapters_opening(more, places=['forest', 'hut', 'tower'])
    table = await start(client, me, friend, more, [], chapters=chapters)
    before = await read_table(client, me, table)

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    after = await read_table(client, me, table)

    assert '숲' not in known_places(before) and '탑' not in known_places(before)
    assert ('gate', 'forest', True) not in known_routes(before, more)
    assert '숲' in known_places(after) and '탑' in known_places(after)
    assert ('gate', 'forest', True) in known_routes(after, more)


async def test_one_cannot_go_to_a_locked_place(client: AsyncClient, me: dict, friend: dict, more: dict, narrated):
    table = await start(client, me, friend, more, [], chapters=chapters_opening(more, places=['forest']))

    refused = await declare(client, me, table, going(more['forest']))
    await play(client, me, friend, table, narrated, mine=going(more['square']))
    await play(client, me, friend, table, narrated, mine=going(more['gate']))
    accepted = await declare(client, me, table, going(more['forest']))

    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert refused.json()['detail'].startswith('action.place')
    assert accepted.status_code == status.HTTP_200_OK, accepted.text


async def test_a_hidden_route_to_a_locked_place_is_not_found(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, more, [], chapters=chapters_opening(more, never(more), places=['cellar']))
    await put_at(session, table, ME, more['square'])
    # 찾을 숨긴 길이 없어 굴리지 않는다
    dice = load_dice(app, [])

    await play(client, me, friend, table, narrated, mine=SEARCHING)

    assert dice.remaining == 0
    assert (await outcome_of(client, me, table, 1, ME))['search']['found'] == []


# --- 사건 ---


async def test_a_happening_into_a_locked_place_waits_for_its_chapter(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    # 광장에 닿으면 지하실로 떨어지는 함정. 지하실은 둘째 장이 연다. 둘째 장도 광장에 닿으면 온다
    table = await start(client, me, friend, more, [trap(more)], chapters=chapters_opening(more, places=['cellar']))

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    waiting = await read_table(client, me, table)
    waited = await events_of(client, me, table, 'happening_occurred')
    await play(client, me, friend, table, narrated)
    fallen = await read_table(client, me, table)

    # 첫 라운드에는 함정의 조건이 채워졌지만 지하실이 닫혀 기다린다. 장은 그 뒤에 넘어간다. 다음 라운드에 떨어진다
    assert (place_of(waiting, ME), waiting['chapter']['id'], waited) == (more['square']['id'], 'later', [])
    assert place_of(fallen, ME) == more['cellar']['id']
    assert len(await events_of(client, me, table, 'happening_occurred')) == 1


# --- 퀘스트 ---


async def test_a_locked_quest_waits_hidden_and_opens_with_its_chapter(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    chapters = chapters_opening(more, quests=['rescue'])
    table = await start(client, me, friend, more, [], chapters=chapters, quests=[rescue(more, time_limit_minutes=60)])
    hidden = await session.execute(
        text('SELECT status, due_at FROM table_quests WHERE entry_id = :id'), {'id': uuid.UUID(more['rescue']['id'])}
    )

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    opened = await read_table(client, me, table)
    await play(client, me, friend, table, narrated)
    done = await read_table(client, me, table)

    # 진행 중으로 시작하지만 닫혀 있어 숨긴 채, 기한도 없다
    assert [tuple(row) for row in hidden.all()] == [('hidden', None)]
    # 광장에 닿은 라운드에 장이 열려 드러난다. 조건은 이미 채워졌지만 이루는 것은 다음 라운드다
    assert (quest_status(opened, '왕녀 구출'), quest_status(done, '왕녀 구출')) == ('active', 'succeeded')
    shown, succeeded = await events_of(client, me, table, 'quest_changed')
    assert (shown['payload']['reason'], shown['payload']['previous'], shown['payload']['status']) == (
        'chapter_opened',
        'hidden',
        'active',
    )
    assert shown['payload']['due_at'] is not None
    assert succeeded['payload']['status'] == 'succeeded'


async def test_a_locked_quest_does_not_succeed_while_locked(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    chapters = chapters_opening(more, never(more), quests=['rescue'])
    table = await start(client, me, friend, more, [], chapters=chapters, quests=[rescue(more)])

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    await play(client, me, friend, table, narrated)

    assert quest_status(await read_table(client, me, table), '왕녀 구출') is None
    assert await events_of(client, me, table, 'quest_changed') == []


# --- 서술 ---


async def test_the_narrator_hears_nothing_of_what_is_locked(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, more: dict, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    chapters = chapters_opening(more, never(more), places=['cellar'], quests=['rescue'])
    table = await start(client, me, friend, more, [], chapters=chapters, quests=[rescue(more)])

    await play(client, me, friend, table, narrated)
    candidates = await load_candidates(app.state.session_factory, uuid.UUID(table['id']))

    (request,) = narrator.requests
    assert '왕녀 구출' not in [quest.name for quest in request.quests]
    names = {entry.name for entry in candidates.entries}
    assert '지하실' not in names and '왕녀 구출' not in names
    assert '광장' in names


async def test_a_table_without_chapters_locks_nothing(client: AsyncClient, me: dict, friend: dict, more: dict):
    table = await start(client, me, friend, more, [])

    seen = await read_table(client, me, table)

    assert seen['chapter'] is None
    assert '숲' in known_places(seen) and '탑' in known_places(seen)
