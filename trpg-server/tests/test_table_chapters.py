# trpg-server/tests/test_table_chapters.py

"""
테이블의 지금 장과 장 넘기기(#481 ②-a, app/tables/chapters.py, app/rounds/chapters.py)를 검증한다.
장이 여는 장소와 퀘스트를 막는 것(열림)은 다음 일이다.

맵과 픽스처는 tests/test_happenings.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 성문(시작)-광장 큰길,
광장→지하실 숨긴 길, 성문-숲 안개 길, 탑은 명소. 사건 항목 셋(함정, 휩쓸림, 왕녀 구출)이 있다.
장은 셋이다. 도착(처음), 지하(광장에 닿으면), 숲(숲에 닿으면).

보는 것.
  - 시작: 장이 있는 판은 첫 장에서 시작한다. 테이블을 읽으면 지금 장(id, 이름, 몇째, 몇 개 중, 넘어온 라운드)이 보인다.
    장이 없는 판은 지금 장이 없다.
  - 넘어가기: 라운드가 닫힐 때 다음 장의 조건이 채워졌으면 넘어간다. 한 번에 한 장이다. 뒤로 가지 않는다.
    이벤트는 chapter_changed 이고, 행한 사람이 없고, 라운드가 닫힌 이벤트보다 앞이며 같은 묶음이다.
  - 차례: 퀘스트와 사건을 본 뒤에 장을 본다. 그 라운드에 넘어간 장을 기다리는 퀘스트와 사건은 다음 라운드에 본다.
  - 조건 chapter_at_least: 퀘스트와 사건의 조건에 쓴다. 대상은 장의 id(chapter)다. 판에 없는 장이면 게시하지 못한다.
    장의 넘어오는 조건에는 쓰지 않는다. 장(chapter)과 대상(target)을 함께 적거나 빠뜨리면 받지 않는다.
  - 서술: 지금 장이 [장]으로 간다. 그 라운드에 넘어왔으면 그것을 그리라는 말이 붙는다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError

from app.assets.scenarios.snapshot import Snapshot
from app.rounds import prompt
from app.rounds.narrator import ChapterNote, NarrationRequest
from app.tables import chapters as table_chapters
from app.transcripts.markdown import render_event
from tests import test_happenings as happening_tests
from tests.narration_model import asset_body
from tests.test_happenings import draft, happening, moving, publish, reach, start
from tests.test_map_actions import going, play
from tests.test_table_items import SCENARIOS_URL, events_of, read_table
from tests.test_table_map import place_of
from tests.test_transcript_markdown import LABELS, event
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = happening_tests.me
friend = happening_tests.friend
lore = happening_tests.lore
more = happening_tests.more


def chapter(key: str, name: str, when: list[dict] | None = None) -> dict:
    return {'id': key, 'name': name, 'when': when or []}


def at_least(key: str) -> dict:
    """지금 장이 그 장 이상이다."""
    return {'kind': 'chapter_at_least', 'chapter': key}


def three_chapters(more: dict) -> list[dict]:
    """도착(처음), 지하(광장에 닿으면), 숲(숲에 닿으면)."""
    return [
        chapter('arrival', '도착'),
        chapter('below', '지하', [reach(more['square'])]),
        chapter('woods', '숲', [reach(more['forest'])]),
    ]


def rescue(more: dict, *conditions: dict) -> dict:
    """진행 중으로 시작하는 왕녀 구출. 조건이 채워지면 이룬다."""
    return {'entry_id': more['rescue']['id'], 'start': 'active', 'conditions': list(conditions)}


# --- 시작 ---


async def test_a_table_starts_at_the_first_chapter(client: AsyncClient, me: dict, friend: dict, more: dict):
    table = await start(client, me, friend, more, [], chapters=three_chapters(more))

    seen = await read_table(client, friend, table)

    assert seen['chapter'] == {'id': 'arrival', 'name': '도착', 'number': 1, 'total': 3, 'entered_round': None}


async def test_a_table_without_chapters_has_no_chapter(client: AsyncClient, me: dict, friend: dict, more: dict):
    table = await start(client, me, friend, more, [])

    assert (await read_table(client, me, table))['chapter'] is None


# --- 넘어가기 ---


async def test_reaching_the_condition_moves_to_the_next_chapter(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    table = await start(client, me, friend, more, [], chapters=three_chapters(more))

    await play(client, me, friend, table, narrated, mine=going(more['square']))

    seen = await read_table(client, friend, table)
    assert seen['chapter'] == {'id': 'below', 'name': '지하', 'number': 2, 'total': 3, 'entered_round': 1}
    (changed,) = await events_of(client, friend, table, 'chapter_changed')
    (closed,) = await events_of(client, friend, table, 'round_closed')
    assert changed['actor_id'] is None
    assert changed['payload'] == {
        'round': 1,
        'from': {'id': 'arrival', 'name': '도착'},
        'to': {'id': 'below', 'name': '지하'},
        'number': 2,
    }
    assert changed['action_group_id'] == closed['action_group_id']
    assert changed['sequence'] < closed['sequence']


async def test_one_chapter_at_a_time_and_never_back(client: AsyncClient, me: dict, friend: dict, more: dict, narrated):
    # 셋째 장도 광장에 닿으면 넘어온다. 그래도 한 라운드에 한 장이다
    chapters = [*three_chapters(more)[:2], chapter('square', '광장', [reach(more['square'])])]
    table = await start(client, me, friend, more, [], chapters=chapters)

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    first = (await read_table(client, me, table))['chapter']
    await play(client, me, friend, table, narrated, mine=going(more['gate']))
    second = (await read_table(client, me, table))['chapter']
    await play(client, me, friend, table, narrated)
    third = (await read_table(client, me, table))['chapter']

    # 둘째 라운드가 닫힐 때 기사는 성문에 섰다. 광장의 조건은 채워지지 않았지만 앞서 넘어온 장은 그대로다
    assert [(seen['id'], seen['entered_round']) for seen in (first, second, third)] == [
        ('below', 1),
        ('below', 1),
        ('below', 1),
    ]
    assert len(await events_of(client, me, table, 'chapter_changed')) == 1


async def test_the_last_chapter_stays(client: AsyncClient, me: dict, friend: dict, more: dict, narrated):
    table = await start(client, me, friend, more, [], chapters=three_chapters(more)[:2])

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    await play(client, me, friend, table, narrated)

    assert (await read_table(client, me, table))['chapter']['id'] == 'below'


# --- 차례와 chapter_at_least ---


async def test_what_waits_for_a_chapter_comes_the_round_after(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    # 지하 장이면 모두 탑으로 휩쓸려 가고, 왕녀 구출을 이룬다. 둘 다 장을 본 다음 라운드에 일어난다
    storm = happening(more['storm'], [at_least('below')], [moving(more['tower'])])
    table = await start(
        client, me, friend, more, [storm], chapters=three_chapters(more), quests=[rescue(more, at_least('below'))]
    )

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    entered = await read_table(client, me, table)
    await play(client, me, friend, table, narrated)
    after = await read_table(client, me, table)

    assert (entered['chapter']['id'], entered['quests'][0]['status'], place_of(entered, happening_tests.ME)) == (
        'below',
        'active',
        more['square']['id'],
    )
    assert (after['quests'][0]['status'], place_of(after, happening_tests.ME)) == ('succeeded', more['tower']['id'])


async def test_a_chapter_condition_is_saved_with_its_chapter(client: AsyncClient, me: dict, more: dict):
    storm = happening(more['storm'], [at_least('below')], [moving(more['tower'])])
    scenario = await draft(client, me, more, [storm])
    url = f'{SCENARIOS_URL}/{scenario["id"]}'
    saved = await client.patch(url, json={'chapters': three_chapters(more)}, headers=me)

    response = await publish(client, me, saved.json())

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert saved.json()['happenings'][0]['when'] == [
        {'kind': 'chapter_at_least', 'chapter': 'below', 'count': 1, 'consume': False}
    ]


async def test_a_chapter_condition_must_point_at_a_chapter(client: AsyncClient, me: dict, more: dict):
    storm = happening(more['storm'], [at_least('nowhere')], [moving(more['tower'])])
    scenario = await draft(client, me, more, [storm])
    url = f'{SCENARIOS_URL}/{scenario["id"]}'
    saved = await client.patch(url, json={'chapters': three_chapters(more)}, headers=me)

    response = await publish(client, me, saved.json())

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['happening_condition_missing']


@pytest.mark.parametrize('case', ['both', 'neither', 'target-only', 'in-chapter-when'])
async def test_a_misshaped_chapter_condition_is_refused(client: AsyncClient, me: dict, more: dict, case: str):
    target = more['square']['id']
    conditions = {
        'both': {'kind': 'chapter_at_least', 'chapter': 'below', 'target': target},
        'neither': {'kind': 'chapter_at_least'},
        'target-only': {'kind': 'chapter_at_least', 'target': target},
        'in-chapter-when': None,
    }
    if case == 'in-chapter-when':
        body = {'title': '성의 모험', 'chapters': [chapter('a', '처음'), chapter('b', '다음', [at_least('a')])]}
    else:
        storm = happening(more['storm'], [conditions[case]], [moving(more['tower'])])
        body = {'title': '성의 모험', 'happenings': [storm]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text


async def test_another_condition_must_not_carry_a_chapter(client: AsyncClient, me: dict, more: dict):
    storm = happening(more['storm'], [{**reach(more['square']), 'chapter': 'below'}], [moving(more['tower'])])
    body = {'title': '성의 모험', 'happenings': [storm]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_snapshot_refuses_a_condition_on_a_missing_chapter(client: AsyncClient, me: dict, more: dict):
    storm = happening(more['storm'], [at_least('below')], [moving(more['tower'])])
    scenario = await draft(client, me, more, [storm])
    url = f'{SCENARIOS_URL}/{scenario["id"]}'
    saved = await client.patch(url, json={'chapters': three_chapters(more)}, headers=me)
    document = (await publish(client, me, saved.json())).json()['snapshot']

    with pytest.raises(ValidationError):
        Snapshot.model_validate({**document, 'chapters': []})
    Snapshot.model_validate(document)


# --- 서술 ---


async def test_the_narrator_hears_the_chapter_and_when_it_began(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, more: dict, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start(client, me, friend, more, [], chapters=three_chapters(more))

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    await play(client, me, friend, table, narrated)

    first, second = narrator.requests
    assert (first.chapter, second.chapter) == (
        ChapterNote(number=2, name='지하', entered=True),
        ChapterNote(number=2, name='지하', entered=False),
    )


def test_the_chapter_lines():
    entered = prompt.chapter_lines(ChapterNote(number=2, name='지하', entered=True))
    staying = prompt.chapter_lines(ChapterNote(number=2, name='지하'))

    assert entered == [prompt.CHAPTER_TITLE, prompt.CHAPTER_NOTE, '- 2장: 지하', prompt.CHAPTER_ENTERED_NOTE, '']
    assert staying == [prompt.CHAPTER_TITLE, prompt.CHAPTER_NOTE, '- 2장: 지하', '']
    assert prompt.chapter_lines(None) == []


def test_the_round_text_carries_the_chapter():
    request = NarrationRequest(round_number=1, scene='성문 앞이다.', moves=[], chapter=ChapterNote(2, '지하', True))

    text = prompt.round_text(request)

    assert '- 2장: 지하' in text
    assert prompt.CHAPTER_ENTERED_NOTE in text


def test_the_transcript_names_the_chapter():
    payload = {'round': 2, 'from': {'id': 'a', 'name': '도착'}, 'to': {'id': 'b', 'name': '지하'}, 'number': 2}

    assert '2장: 지하' in render_event(event('chapter_changed', payload), LABELS)


# --- 작은 함수 ---


def table_at(chapter_id: str | None, ids: list[str]) -> SimpleNamespace:
    # 지나온 장(chapter_path)을 적기 전에 시작한 테이블이다. 판의 첫 장부터 지금 장까지로 본다(#289)
    return SimpleNamespace(chapter_id=chapter_id, chapter_path=[], content={'chapters': [{'id': one} for one in ids]})


def test_at_least_counts_the_chapter_and_those_after():
    ids = ['a', 'b', 'c']

    assert table_chapters.at_least(table_at('b', ids), 'a')
    assert table_chapters.at_least(table_at('b', ids), 'b')
    assert not table_chapters.at_least(table_at('b', ids), 'c')
    assert not table_chapters.at_least(table_at(None, ids), 'a')
    assert not table_chapters.at_least(table_at('b', ids), str(uuid.uuid4()))
    assert not table_chapters.at_least(SimpleNamespace(chapter_id=None, chapter_path=[], content={}), 'a')
