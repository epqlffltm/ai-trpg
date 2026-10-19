# trpg-server/tests/test_whispers.py

"""
테이블 안의 1:1 쪽지(#196).

보는 것은 다섯이다.
  - 보낸 사람과 받은 사람만 본다. 방장도, 다른 사람도 보지 못한다. 번호의 빈칸으로도 새지 않는다.
  - 보낼 수 있는 때와 상대가 정해져 있다(앉은 사람, 끝나지 않은 테이블, 자기 자신은 안 됨).
  - 알림(whisper_notice)을 켠 테이블에만 "누가 누구에게 보냈다"가 이벤트로 남는다. 글은 남지 않는다.
  - 스트림으로 자기 쪽지함의 것만 온다.
  - GM 에게 보이기로 한 쪽지만 서술에 들어간다. 보낸 사람마다 최근 몇 장까지다.
"""

import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import MESSAGE_MAX_LENGTH
from app.events.models import TableEvent
from app.limits.setup import build_limiting
from app.main import API_PREFIX
from app.realtime.service import Cursor
from app.rounds import prompt
from app.rounds.models import Round
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview, WhisperNote
from app.rounds.service import GM_WHISPERS_PER_SENDER
from app.tables.models import GameTable
from app.whispers.models import Whisper
from app.whispers.service import target_round
from tests.conftest import make_test_settings
from tests.narration_model import with_model
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token
from tests.test_chat_api import make_table

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
THIRD = uuid.UUID('33333333-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
OPENINGS = ['사이렌이 울린다. 망치를 든 드워프가 쫓아온다.']
SECRET = '오늘 밤 성문을 열어 둬.'
REPLY = '알았다. 자정에.'
NAMES = {ME: '엘프', FRIEND: '영애', THIRD: '기사'}


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 테이블을 여는 방장이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def third(signing_key: SigningKey) -> dict[str, str]:
    """세 번째로 앉는 사람의 머리말. 쪽지를 받지 않는 제삼자다."""
    return bearer(signing_key, THIRD)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def table_url(table: dict, path: str = '') -> str:
    """테이블의 주소."""
    return f'{TABLES_URL}/{table["id"]}{path}'


async def open_trio(client: AsyncClient, host: dict, *guests: dict, **options) -> dict:
    """첫 사람이 테이블을 열고 나머지가 들어온다. 아직 시작하지 않았고, 아무도 캐릭터가 없다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=host)
    body = {'title': '밀서', 'rulebook_id': rulebook.json()['id'], 'openings': OPENINGS, 'default_sheet': SHEET}
    scenario = (await client.post(SCENARIOS_URL, json=with_model(body), headers=host)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=host)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 3, **options}
    response = await client.post(TABLES_URL, json=body, headers=host)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    table = response.json()
    for guest in guests:
        joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=guest)
        assert joined.status_code == status.HTTP_200_OK, joined.text
    return table


async def name_all(client: AsyncClient, table: dict, people: dict[uuid.UUID, dict]) -> None:
    """앉은 사람마다 캐릭터를 정한다(NAMES)."""
    for user_id, headers in people.items():
        named = await client.put(table_url(table, '/character'), json={'name': NAMES[user_id]}, headers=headers)
        assert named.status_code == status.HTTP_200_OK, named.text


async def start(client: AsyncClient, table: dict, people: dict[uuid.UUID, dict]) -> None:
    """모두 캐릭터를 정하고 방장(첫 사람)이 시작한다."""
    await name_all(client, table, people)
    started = await client.post(table_url(table, '/start'), headers=next(iter(people.values())))
    assert started.status_code == status.HTTP_200_OK, started.text


async def try_whisper(client: AsyncClient, headers: dict, table: dict, to: uuid.UUID | str, **body):
    """쪽지를 보내 본다. 응답을 그대로 돌려준다."""
    payload = {'recipient_id': str(to), 'content': SECRET, **body}
    return await client.post(table_url(table, '/whispers'), json=payload, headers=headers)


async def whisper(client: AsyncClient, headers: dict, table: dict, to: uuid.UUID, **body) -> dict:
    """쪽지를 보내고, 보낸 사람의 쪽지함에 적힌 것을 돌려준다."""
    response = await try_whisper(client, headers, table, to, **body)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def mailbox(client: AsyncClient, headers: dict, table: dict, **params) -> dict:
    """자기 쪽지함의 한 쪽을 읽는다."""
    response = await client.get(table_url(table, '/whispers'), params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def lines(page: dict) -> list[tuple[int, str, str, str]]:
    """쪽지함의 쪽지를 (번호, 보낸 사람, 받은 사람, 글)로."""
    return [(item['sequence'], item['sender_id'], item['recipient_id'], item['content']) for item in page['items']]


async def events_of(client: AsyncClient, headers: dict, table: dict, kind: str) -> list[dict]:
    """테이블의 이벤트 중 이 종류의 것."""
    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return [event for event in response.json()['items'] if event['type'] == kind]


# --- 로그인 ---


@pytest.mark.parametrize('method', ['GET', 'POST'])
async def test_every_address_requires_login(client: AsyncClient, method: str):
    response = await client.request(method, f'{TABLES_URL}/{NO_SUCH_ID}/whispers', json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 보낸 사람과 받은 사람만 본다 ---


async def test_the_two_see_it_and_the_third_does_not(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)

    sent = await whisper(client, me, table, FRIEND)

    assert (sent['sequence'], sent['sender_id'], sent['recipient_id'], sent['content']) == (
        1,
        str(ME),
        str(FRIEND),
        SECRET,
    )
    assert sent['created_at'] is not None
    assert lines(await mailbox(client, friend, table)) == [(1, str(ME), str(FRIEND), SECRET)]
    nothing = await mailbox(client, third, table)
    assert nothing == {'items': [], 'last_sequence': 0}


async def test_the_host_cannot_read_the_others_whispers(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)

    await whisper(client, friend, table, THIRD)

    # 방장도 제삼자다
    assert await mailbox(client, me, table) == {'items': [], 'last_sequence': 0}


async def test_each_mailbox_counts_its_own_numbers(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)

    await whisper(client, me, table, FRIEND)
    await whisper(client, friend, table, THIRD, content=REPLY)
    await whisper(client, me, table, FRIEND, content='하나 더.')

    # 내 번호는 나와 상관있는 쪽지로만 올라간다. 남이 주고받은 쪽지 때문에 번호가 건너뛰지 않는다
    mine, friends, thirds = [lines(await mailbox(client, headers, table)) for headers in (me, friend, third)]
    assert [line[0] for line in mine] == [1, 2]
    assert [line[0] for line in friends] == [1, 2, 3]
    assert thirds == [(1, str(FRIEND), str(THIRD), REPLY)]


async def test_whispers_leave_no_gap_in_the_chat(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)

    await whisper(client, me, table, FRIEND)
    said = await client.post(table_url(table, '/messages'), json={'content': '안녕'}, headers=third)

    # 채팅의 번호는 그대로다. 쪽지가 오간 것이 채팅의 번호로 드러나지 않는다
    assert said.json()['sequence'] == 1
    chat = await client.get(table_url(table, '/messages'), headers=third)
    assert chat.json()['last_sequence'] == 1
    assert SECRET not in chat.text


async def test_a_whisper_carries_the_names_of_that_moment(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)
    before = await whisper(client, me, table, FRIEND)

    await name_all(client, table, {ME: me, FRIEND: friend})
    after = await whisper(client, me, table, FRIEND)

    assert (before['sender_character_name'], before['recipient_character_name']) == (None, None)
    assert (after['sender_character_name'], after['recipient_character_name']) == ('엘프', '영애')


async def test_reads_only_what_comes_after(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)
    for content in ('하나', '둘', '셋'):
        await whisper(client, me, table, FRIEND, content=content)

    page = await mailbox(client, friend, table, after=1, limit=1)

    assert [item['content'] for item in page['items']] == ['둘']
    assert page['last_sequence'] == 3


# --- 보낼 수 있는 때와 상대 ---


async def test_cannot_whisper_to_oneself(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)

    response = await try_whisper(client, me, table, ME)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'recipient_id' in response.text


@pytest.mark.parametrize('to', [STRANGER, NO_SUCH_ID])
async def test_cannot_whisper_to_someone_not_seated(client: AsyncClient, me: dict, friend: dict, third: dict, to):
    table = await open_trio(client, me, friend, third)

    response = await try_whisper(client, me, table, to)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await mailbox(client, me, table) == {'items': [], 'last_sequence': 0}


async def test_those_not_seated_see_no_table(client: AsyncClient, me: dict, friend: dict, third: dict, stranger: dict):
    table = await open_trio(client, me, friend, third)
    await whisper(client, me, table, FRIEND)

    reading = await client.get(table_url(table, '/whispers'), headers=stranger)
    writing = await try_whisper(client, stranger, table, ME)

    assert (reading.status_code, writing.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    assert SECRET not in reading.text


@pytest.mark.parametrize(
    'body',
    [
        {'content': ''},
        {'content': '   '},
        {'content': '가' * (MESSAGE_MAX_LENGTH + 1)},
        {'content': '안녕', 'sender_id': str(FRIEND)},
        {'recipient_id': 'nobody'},
    ],
    ids=['empty', 'blank', 'too-long', 'extra-field', 'bad-recipient'],
)
async def test_rejects_a_bad_whisper(client: AsyncClient, me: dict, friend: dict, third: dict, body: dict):
    table = await open_trio(client, me, friend, third)

    response = await client.post(
        table_url(table, '/whispers'), json={'recipient_id': str(FRIEND), 'content': SECRET, **body}, headers=me
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_an_ended_table_keeps_its_whispers_but_takes_no_new_ones(
    client: AsyncClient, me: dict, friend: dict, third: dict
):
    table = await open_trio(client, me, friend, third)
    await whisper(client, me, table, FRIEND)

    await client.post(table_url(table, '/end'), headers=me)
    response = await try_whisper(client, me, table, FRIEND, content='늦었다.')

    assert response.status_code == status.HTTP_409_CONFLICT
    assert lines(await mailbox(client, friend, table)) == [(1, str(ME), str(FRIEND), SECRET)]


async def test_someone_kicked_reads_and_receives_no_more(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)
    await whisper(client, me, table, FRIEND)

    await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)

    reading = await client.get(table_url(table, '/whispers'), headers=friend)
    sending = await try_whisper(client, third, table, FRIEND)
    assert (reading.status_code, sending.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)


async def test_a_mailbox_keeps_counting_after_leaving_and_coming_back(
    client: AsyncClient, me: dict, friend: dict, third: dict
):
    table = await open_trio(client, me, friend, third)
    await whisper(client, me, table, FRIEND)

    await client.delete(table_url(table, '/members/me'), headers=friend)
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await whisper(client, me, table, FRIEND, content=REPLY)

    # 쪽지함은 자리와 따로 남는다. 다시 앉으면 자기 쪽지가 그대로 있고, 번호가 겹치지 않는다
    assert lines(await mailbox(client, friend, table)) == [
        (1, str(ME), str(FRIEND), SECRET),
        (2, str(ME), str(FRIEND), REPLY),
    ]


async def test_whispers_count_with_the_chat(client: AsyncClient, app: FastAPI, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)
    app.state.limiting = build_limiting(make_test_settings(limits_enabled=True), None)

    said = [
        (await client.post(table_url(table, '/messages'), json={'content': '안녕'}, headers=me)).status_code
        for _ in range(3)
    ]
    sent = [(await try_whisper(client, me, table, FRIEND)).status_code for _ in range(3)]

    # 채팅 셋과 쪽지 둘로 다섯 줄이다. 쪽지로 채팅의 제한을 돌아가지 못한다
    assert said == [status.HTTP_201_CREATED] * 3
    assert sent == [status.HTTP_201_CREATED] * 2 + [status.HTTP_429_TOO_MANY_REQUESTS]


# --- 보낸 사실의 알림 ---


async def test_by_default_nobody_is_told(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)
    before = await client.get(table_url(table, '/events'), headers=third)

    await whisper(client, me, table, FRIEND)

    after = await client.get(table_url(table, '/events'), headers=third)
    assert table['whisper_notice'] is False
    assert after.json() == before.json()


async def test_with_the_notice_on_everyone_learns_who_whispered_to_whom(
    client: AsyncClient, me: dict, friend: dict, third: dict, session: AsyncSession
):
    table = await open_trio(client, me, friend, third)
    await name_all(client, table, {ME: me, FRIEND: friend})
    changed = await client.put(table_url(table, '/whisper-notice'), json={'whisper_notice': True}, headers=me)

    await whisper(client, me, table, FRIEND)

    assert changed.status_code == status.HTTP_200_OK, changed.text
    assert changed.json()['whisper_notice'] is True
    (notice,) = await events_of(client, third, table, 'whisper_notice_changed')
    assert notice['payload'] == {'whisper_notice': True}
    (sent,) = await events_of(client, third, table, 'whisper_sent')
    assert sent['actor_id'] == str(ME)
    assert sent['payload'] == {
        'user_id': str(ME),
        'character_name': '엘프',
        'recipient_id': str(FRIEND),
        'recipient_character_name': '영애',
    }
    # 글은 이벤트 어디에도 없다. 내보낼 때 거르는 것이 아니라 처음부터 적지 않는다
    events = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=third)
    assert SECRET not in events.text
    stored = await session.scalar(select(TableEvent.payload).where(TableEvent.type == 'whisper_sent'))
    assert SECRET not in json.dumps(stored, ensure_ascii=False)
    assert set(stored) == {'user_id', 'character_name', 'recipient_id', 'recipient_character_name'}


async def test_the_notice_follows_the_option_of_the_moment(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third, whisper_notice=True)
    await whisper(client, me, table, FRIEND)

    await client.put(table_url(table, '/whisper-notice'), json={'whisper_notice': False}, headers=me)
    await whisper(client, me, table, FRIEND)

    # 만들 때 켰다. 끈 뒤에 보낸 것은 알리지 않는다
    assert table['whisper_notice'] is True
    assert len(await events_of(client, third, table, 'whisper_sent')) == 1


async def test_only_the_host_changes_the_notice(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)

    response = await client.put(table_url(table, '/whisper-notice'), json={'whisper_notice': True}, headers=friend)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert await events_of(client, me, table, 'whisper_notice_changed') == []


async def test_the_same_notice_leaves_no_event(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)

    response = await client.put(table_url(table, '/whisper-notice'), json={'whisper_notice': False}, headers=me)

    assert response.status_code == status.HTTP_200_OK
    assert await events_of(client, me, table, 'whisper_notice_changed') == []


@pytest.mark.parametrize('body', [{}, {'whisper_notice': 'maybe'}, {'whisper_notice': True, 'extra': 1}])
async def test_rejects_a_bad_notice(client: AsyncClient, me: dict, friend: dict, third: dict, body: dict):
    table = await open_trio(client, me, friend, third)

    response = await client.put(table_url(table, '/whisper-notice'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_notice_cannot_change_on_an_ended_table(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)
    await client.post(table_url(table, '/end'), headers=me)

    response = await client.put(table_url(table, '/whisper-notice'), json={'whisper_notice': True}, headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_the_lobby_shows_the_notice(client: AsyncClient, me: dict, stranger: dict):
    await open_trio(client, me, is_public=True, whisper_notice=True)

    lobby = await client.get(f'{TABLES_URL}/lobby', headers=stranger)

    assert lobby.status_code == status.HTTP_200_OK, lobby.text
    assert [item['whisper_notice'] for item in lobby.json()['items']] == [True]


# --- 스트림 ---


async def test_a_whisper_reaches_only_the_two_streams(
    client: AsyncClient, me: dict, friend: dict, third: dict, connect
):
    table = await open_trio(client, me, friend, third)
    mine, friends, thirds = (connect(table, user_id, Cursor(events=3)) for user_id in (ME, FRIEND, THIRD))
    for reader in (mine, friends, thirds):
        await reader.settle()

    await whisper(client, me, table, FRIEND)

    for reader in (mine, friends):
        frame = await reader.next()
        assert (frame.event, frame.id) == ('whisper', '3-0-1')
        assert json.loads(frame.data)['content'] == SECRET
    assert await thirds.is_quiet()


async def test_coming_back_picks_up_the_whispers_where_it_left_off(
    client: AsyncClient, me: dict, friend: dict, third: dict, connect
):
    table = await open_trio(client, me, friend, third)
    await whisper(client, me, table, FRIEND, content='하나')
    first = connect(table, FRIEND, Cursor(events=3))
    last = await first.next()
    await first.close()

    await whisper(client, me, table, FRIEND, content='둘')
    again = connect(table, FRIEND, Cursor(events=3, whispers=int(last.id.split('-')[2])))

    frame = await again.next()
    assert (frame.id, json.loads(frame.data)['content']) == ('3-0-2', '둘')
    assert await again.is_quiet()


async def test_the_stream_address_takes_the_whisper_number(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await open_trio(client, me, friend, third)
    await whisper(client, me, table, FRIEND, content='하나')
    await whisper(client, me, table, FRIEND, content='둘')
    await client.post(table_url(table, '/end'), headers=me)

    # 끝난 테이블의 스트림은 남은 것을 보내고 닫힌다. 쪽지는 주소의 번호 뒤의 것만 온다
    response = await client.get(
        table_url(table, '/stream'),
        params={'events_after': 4, 'messages_after': 0, 'whispers_after': 1},
        headers=friend,
    )

    whispers = [line for line in response.text.splitlines() if line.startswith('data:') and '"sender_id"' in line]
    assert len(whispers) == 1
    assert '둘' in whispers[0]


# --- GM 에게 ---


@dataclass
class RecordingNarrator:
    """받은 요청을 적어 두고 정해 둔 글을 돌려주는 서술자."""

    requests: list[NarrationRequest] = field(default_factory=list)

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.requests.append(request)
        return f'{request.round_number} 라운드의 장면'


@pytest.fixture
def recording(app: FastAPI) -> RecordingNarrator:
    """앱의 서술자를 받은 요청을 적어 두는 것으로 바꾼다."""
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    return narrator


async def declare_all(client: AsyncClient, table: dict, people: dict[uuid.UUID, dict]) -> None:
    """모두 선언한다. 다 내면 라운드가 닫기 시작한다."""
    url = table_url(table, '/rounds/current/declaration')
    for headers in people.values():
        declared = await client.put(url, json={'content': '주위를 살핀다.'}, headers=headers)
        assert declared.status_code == status.HTTP_200_OK, declared.text


async def test_only_whispers_shown_to_the_gm_reach_the_narration(
    client: AsyncClient, me: dict, friend: dict, third: dict, recording: RecordingNarrator, narrated
):
    people = {ME: me, FRIEND: friend, THIRD: third}
    table = await open_trio(client, me, friend, third)
    await start(client, table, people)

    await whisper(client, me, table, FRIEND, content='GM 은 모른다.')
    await whisper(client, friend, table, THIRD, content=SECRET, gm_visible=True)
    await declare_all(client, table, people)
    await narrated()

    (request,) = recording.requests
    assert request.whispers == [WhisperNote(sender='영애', recipient='기사', content=SECRET)]
    # 받은 사람도 GM 이 봤는지 안다
    assert [item['gm_visible'] for item in (await mailbox(client, third, table))['items']] == [True]
    assert [item['gm_visible'] for item in (await mailbox(client, friend, table))['items']] == [False, True]


async def test_whispers_before_the_start_go_to_the_first_round(
    client: AsyncClient, me: dict, friend: dict, third: dict, recording: RecordingNarrator, narrated
):
    people = {ME: me, FRIEND: friend, THIRD: third}
    table = await open_trio(client, me, friend, third)
    sent = await whisper(client, me, table, FRIEND, gm_visible=True)

    await start(client, table, people)
    await declare_all(client, table, people)
    await narrated()

    assert sent['round'] == 1
    # 캐릭터를 정하기 전에 보냈다. 이름 없이 간다
    assert recording.requests[0].whispers == [WhisperNote(sender=None, recipient=None, content=SECRET)]


async def test_a_whisper_belongs_to_one_round_only(
    client: AsyncClient, me: dict, friend: dict, third: dict, recording: RecordingNarrator, narrated
):
    people = {ME: me, FRIEND: friend, THIRD: third}
    table = await open_trio(client, me, friend, third)
    await start(client, table, people)
    await whisper(client, me, table, FRIEND, content='첫 라운드', gm_visible=True)
    await declare_all(client, table, people)
    await narrated()

    second = await whisper(client, me, table, FRIEND, content='둘째 라운드', gm_visible=True)
    await declare_all(client, table, people)
    await narrated()

    assert second['round'] == 2
    assert [[note.content for note in request.whispers] for request in recording.requests] == [
        ['첫 라운드'],
        ['둘째 라운드'],
    ]


async def test_the_gm_gets_only_the_latest_few_from_each_sender(
    client: AsyncClient, me: dict, friend: dict, third: dict, recording: RecordingNarrator, narrated
):
    people = {ME: me, FRIEND: friend, THIRD: third}
    table = await open_trio(client, me, friend, third)
    await start(client, table, people)

    await whisper(client, friend, table, THIRD, content='친구의 쪽지', gm_visible=True)
    for number in range(GM_WHISPERS_PER_SENDER + 2):
        await whisper(client, me, table, FRIEND, content=f'내 쪽지 {number}', gm_visible=True)
    await declare_all(client, table, people)
    await narrated()

    # 한 사람이 쏟아 내도 다른 사람의 쪽지가 밀려나지 않는다. 보낸 순서다(보낸 사람의 순서가 아니다)
    mine = [f'내 쪽지 {number}' for number in range(2, GM_WHISPERS_PER_SENDER + 2)]
    assert [note.content for note in recording.requests[0].whispers] == ['친구의 쪽지', *mine]


NOW = datetime(2026, 10, 13, tzinfo=UTC)


def round_of(number: int, closing: bool = False, closed: bool = False) -> Round:
    """번호와 상태(닫기 시작했나, 닫혔나)만 정한 라운드. 저장하지 않는다."""
    return Round(number=number, closing_at=NOW if closing else None, closed_at=NOW if closed else None)


@pytest.mark.parametrize(
    ('latest', 'expected'),
    [
        (None, 1),
        (round_of(3), 3),
        (round_of(3, closing=True), 4),
        (round_of(3, closing=True, closed=True), 4),
    ],
    ids=['not-started', 'open', 'closing', 'closed'],
)
def test_a_whisper_goes_to_the_open_round_or_the_next(latest: Round | None, expected: int):
    # 닫기 시작한 라운드에는 더 넣지 않는다. 서술을 다시 맡겨도 같은 쪽지를 받는다
    assert target_round(latest) == expected


# --- 서술의 글 ---


def make_request(*whispers: WhisperNote) -> NarrationRequest:
    """쪽지만 정한 서술 요청."""
    return replace(NarrationRequest(round_number=2, scene='성문 앞.', moves=[]), whispers=list(whispers))


def test_the_prompt_lists_the_whispers_as_hidden():
    text = prompt.round_text(make_request(WhisperNote('엘프', '영애', SECRET), WhisperNote(None, '기사', REPLY)))

    assert prompt.WHISPER_TITLE in text
    assert prompt.WHISPER_NOTE in text
    assert f'- 엘프 → 영애: {SECRET}' in text
    assert f'- {prompt.UNNAMED_PLAYER} → 기사: {REPLY}' in text
    # 쪽지는 이번 라운드의 차례보다 앞이다
    assert text.index(prompt.WHISPER_TITLE) < text.index('[2 라운드에 한 일과 결과]')


def test_no_whispers_no_section():
    assert prompt.WHISPER_TITLE not in prompt.round_text(make_request())


# --- DB 의 마지막 방어선 ---


def make_whisper(table: GameTable, owner: uuid.UUID, sequence: int, **fields) -> Whisper:
    """서비스를 거치지 않고 쪽지 한 장을 만든다."""
    values = {'sender_id': ME, 'recipient_id': FRIEND, 'content': SECRET, 'round_number': 1, **fields}
    return Whisper(table_id=table.id, owner_id=owner, sequence=sequence, **values)


async def test_the_database_rejects_two_whispers_with_the_same_number_in_one_mailbox(session: AsyncSession):
    table = await make_table(session)
    session.add_all([make_whisper(table, ME, 1), make_whisper(table, FRIEND, 1)])
    await session.commit()

    session.add(make_whisper(table, ME, 1))

    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.parametrize(
    'fields',
    [
        {'owner': THIRD},
        {'recipient_id': ME},
        {'sequence': 0},
        {'round_number': 0},
        {'content': '가' * (MESSAGE_MAX_LENGTH + 1)},
    ],
    ids=['third-party-mailbox', 'to-self', 'sequence-zero', 'round-zero', 'too-long'],
)
async def test_the_database_rejects_a_bad_whisper(session: AsyncSession, fields: dict):
    table = await make_table(session)
    owner = fields.pop('owner', ME)
    sequence = fields.pop('sequence', 1)

    session.add(make_whisper(table, owner, sequence, **fields))

    with pytest.raises(IntegrityError):
        await session.commit()
