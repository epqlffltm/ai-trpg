# trpg-server/tests/test_transcripts_api.py

"""
한 판의 기록을 마크다운 파일로 내려받는 것(#403)을 검증한다.

  - GET /tables/{id}/transcript: 앉은 사람
  - GET /tables/past/{id}/transcript: 떠난 사람
픽스처와 도우미는 tests/test_events_api.py 의 것이다.

보는 것.
  - 마크다운 파일로 온다. 이름은 테이블의 제목이다.
  - 시작, 라운드, 스타팅의 서술, 선언, 결과의 서술이 차례대로 있다.
  - 쪽지의 글, GM 전용 글(진행 지침), 내부 식별자는 없다.
  - 떠난 사람은 떠난 때까지만 받는다. 그 뒤의 서술은 없다.
  - 앉지 않은 사람, 떠난 적 없는 사람은 404, 로그인하지 않으면 401 이다.
  - 이벤트는 쪽마다 읽어 빠짐없이 차례대로 나온다.
"""

import re
import uuid
from urllib.parse import quote

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.transcripts import reading
from app.transcripts.labels import Labels
from tests import test_events_api as event_tests
from tests.test_events_api import (
    FRIENDS_ACTION,
    GM_GUIDE,
    MY_ACTION,
    NO_SUCH_ID,
    OPENINGS,
    declare,
    read_events,
    start_duo,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

# 이벤트 테스트의 픽스처를 그대로 쓴다. 나(방장), 친구, 앉지 않는 사람
me = event_tests.me
friend = event_tests.friend
stranger = event_tests.stranger

UUID_PATTERN = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
SECRET = '비밀 통로는 와인 창고 뒤에 있다'
TABLES_URL = event_tests.TABLES_URL


def transcript_url(table: dict) -> str:
    return table_url(table, '/transcript')


def past_transcript_url(table: dict) -> str:
    return f'{TABLES_URL}/past/{table["id"]}/transcript'


async def play_a_round(client: AsyncClient, me: dict, friend: dict, table: dict, narrated) -> None:
    """둘 다 선언해 라운드를 닫고 서술이 끝나기를 기다린다."""
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()


async def download(client: AsyncClient, url: str, headers: dict) -> str:
    response = await client.get(url, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.text


async def test_one_seated_downloads_the_story(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    await play_a_round(client, me, friend, table, narrated)

    response = await client.get(transcript_url(table), headers=me)
    text = response.text
    events = await read_events(client, me, table, limit=100)
    narrations = [event['payload']['text'] for event in events if event['type'] == 'gm_narration']

    assert response.status_code == status.HTTP_200_OK
    assert response.headers['content-type'] == 'text/markdown; charset=utf-8'
    disposition = response.headers['content-disposition']
    assert disposition.startswith('attachment;') and f"filename*=UTF-8''{quote(table['title'] + '.md')}" in disposition
    assert text.startswith(f'# {table["title"]}\n')
    # 차례대로다. 시작, 1 라운드와 그 장면(스타팅), 선언, 2 라운드와 그 장면(결과의 서술)
    order = ['## 시작', '## 라운드 1', OPENINGS[0], f'> {MY_ACTION}', f'> {FRIENDS_ACTION}']
    order += ['## 라운드 2', narrations[-1]]
    positions = [text.index(piece) for piece in order]
    assert positions == sorted(positions)
    assert '- 함께한 캐릭터: 엘프, 영애' in text


async def test_secrets_and_ids_are_left_out(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    whispered = await client.post(
        table_url(table, '/whispers'), json={'recipient_id': str(event_tests.FRIEND), 'content': SECRET}, headers=me
    )
    assert whispered.status_code == status.HTTP_201_CREATED, whispered.text
    await play_a_round(client, me, friend, table, narrated)

    text = await download(client, transcript_url(table), me)

    assert SECRET not in text
    assert GM_GUIDE not in text
    assert UUID_PATTERN.search(text) is None


async def test_one_who_left_gets_up_to_leaving(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    left = await client.delete(table_url(table, '/members/me'), headers=friend)
    assert left.status_code == status.HTTP_204_NO_CONTENT, left.text
    # 남은 사람이 이어 간다. 혼자 선언하면 라운드가 닫히고 결과가 서술된다
    await declare(client, me, table, MY_ACTION)
    await narrated()

    mine = await download(client, transcript_url(table), me)
    theirs = await download(client, past_transcript_url(table), friend)

    assert '(떠난 때까지)' in theirs
    assert theirs.rstrip().endswith('- 영애: 테이블을 나감')
    assert MY_ACTION in mine and MY_ACTION not in theirs
    assert '## 라운드 2' in mine and '## 라운드 2' not in theirs


async def test_only_those_who_sat_get_it(client: AsyncClient, me: dict, friend: dict, stranger: dict):
    table = await start_duo(client, me, friend)

    assert (await client.get(transcript_url(table), headers=stranger)).status_code == status.HTTP_404_NOT_FOUND
    # 떠난 적이 없는 사람은 떠난 사람의 길로 받지 못한다(앉은 사람의 길로 받는다)
    assert (await client.get(past_transcript_url(table), headers=me)).status_code == status.HTTP_404_NOT_FOUND
    unknown = {'id': NO_SUCH_ID}
    assert (await client.get(transcript_url(unknown), headers=me)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(transcript_url(table))).status_code == status.HTTP_401_UNAUTHORIZED
    assert (await client.get(past_transcript_url(table))).status_code == status.HTTP_401_UNAUTHORIZED


async def test_events_are_read_page_by_page_in_order(app: FastAPI, client: AsyncClient, me: dict, friend: dict):
    table = await start_duo(client, me, friend)
    stored = [event['sequence'] for event in await read_events(client, me, table)]
    cut = reading.Cut(table_id=uuid.UUID(table['id']), title='', until=stored[-1], departed=False, labels=Labels())

    read = [event.sequence async for event in reading.iter_events(app.state.session_factory, cut, page_size=2)]
    stops_early = reading.Cut(table_id=cut.table_id, title='', until=3, departed=False, labels=Labels())
    early = [event.sequence async for event in reading.iter_events(app.state.session_factory, stops_early, page_size=2)]

    assert read == stored
    assert early == [1, 2, 3]


async def test_the_names_come_from_the_table_s_rules(
    client: AsyncClient, session: AsyncSession, me: dict, friend: dict
):
    table = await start_duo(client, me, friend)
    rules = (await client.get(table_url(table), headers=me)).json()['rules']

    cut = await reading.seated_cut(session, event_tests.ME, uuid.UUID(table['id']))

    assert cut.labels.abilities == {ability['key']: ability['name'] for ability in rules['abilities']}
    assert cut.labels.difficulties == {level['key']: level['name'] for level in rules['difficulties']}
    assert cut.labels.injuries == {injury['key']: injury['name'] for injury in rules['injuries']}
