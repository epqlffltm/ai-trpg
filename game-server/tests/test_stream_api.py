# game-server/tests/test_stream_api.py

"""
스트림의 HTTP 쪽을 검증한다. 인증, 누가 붙을 수 있나, 응답의 모양.

테스트용 클라이언트는 응답이 끝나야 결과를 돌려준다. 그래서 끝나는 스트림만 여기서 본다.
끝난 테이블의 스트림은 밀린 것을 보내고 스스로 닫힌다.
끝나지 않는 스트림(실시간으로 받기)은 tests/test_stream.py 가 본다.
"""

import json
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient, Response

from app.main import API_PREFIX
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
OPENINGS = ['사이렌이 울린다. 망치를 든 드워프가 쫓아온다.']
GM_GUIDE = '진지한 장면은 금지다. 모든 추격은 바이크로 한다.'
HELLO = '나는 엘프 할게. 바이크는 내가 몬다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 테이블을 여는 방장이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def stream_url(table: dict) -> str:
    """테이블의 스트림 주소."""
    return f'{TABLES_URL}/{table["id"]}/stream'


async def open_ended_table(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """
    나와 친구가 앉았다가 끝난 테이블. 이벤트가 셋(만들어짐, 들어옴, 끝남), 채팅이 하나 있다.

    끝난 테이블의 스트림은 밀린 것을 보내고 닫힌다. 응답이 끝나므로 테스트용 클라이언트로 받을 수 있다.
    """
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북', 'gm_guide': GM_GUIDE}, headers=me)
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': OPENINGS, 'default_sheet': SHEET}
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    table = (await client.post(TABLES_URL, json=body, headers=me)).json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await client.post(f'{TABLES_URL}/{table["id"]}/messages', json={'content': HELLO}, headers=me)
    ended = await client.post(f'{TABLES_URL}/{table["id"]}/end', headers=me)
    assert ended.status_code == status.HTTP_200_OK, ended.text
    return table


def parse(response: Response) -> list[dict]:
    """
    응답의 글자를 메시지들로 나눈다. 브라우저가 하는 일이다.

    빈 줄이 메시지의 끝이다. ':' 로 시작하는 줄(주석)은 버린다.
    """
    messages = []
    for block in response.text.split('\n\n'):
        fields = dict(line.split(': ', 1) for line in block.split('\n') if line and not line.startswith(':'))
        if fields:
            messages.append({'id': fields.get('id'), 'event': fields['event'], 'data': json.loads(fields['data'])})
    return messages


# --- 누가 붙을 수 있나 ---


async def test_the_stream_requires_login(client: AsyncClient):
    response = await client.get(f'{TABLES_URL}/{NO_SUCH_ID}/stream')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_a_token_in_the_address_is_not_accepted(client: AsyncClient, me: dict, friend: dict):
    table = await open_ended_table(client, me, friend)
    token = me['Authorization'].removeprefix('Bearer ')

    response = await client.get(stream_url(table), params={'token': token, 'access_token': token})

    # 토큰은 머리말로만 받는다. 주소에 적힌 것은 로그에 남는다
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_the_stream_looks_like_it_does_not_exist_to_those_not_seated(
    client: AsyncClient, me: dict, friend: dict, stranger: dict
):
    table = await open_ended_table(client, me, friend)

    outsider = await client.get(stream_url(table), headers=stranger)
    missing = await client.get(f'{TABLES_URL}/{NO_SUCH_ID}/stream', headers=me)

    # 스트림을 시작하기 전에 거절한다. 평범한 404 다. 없는 테이블과 똑같이 보인다
    assert outsider.status_code == status.HTTP_404_NOT_FOUND
    assert outsider.headers['content-type'] == 'application/json'
    assert outsider.json() == missing.json()
    assert HELLO not in outsider.text


@pytest.mark.parametrize('params', [{'events_after': -1}, {'messages_after': -1}, {'events_after': 'abc'}])
async def test_rejects_bad_starting_points(client: AsyncClient, me: dict, friend: dict, params: dict):
    table = await open_ended_table(client, me, friend)

    response = await client.get(stream_url(table), params=params, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_rejects_a_bad_last_event_id(client: AsyncClient, me: dict, friend: dict):
    table = await open_ended_table(client, me, friend)

    response = await client.get(stream_url(table), headers={**me, 'Last-Event-ID': '어제쯤'.encode().hex()})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 응답의 모양 ---


async def test_the_response_is_an_event_stream(client: AsyncClient, me: dict, friend: dict):
    table = await open_ended_table(client, me, friend)

    response = await client.get(stream_url(table), headers=friend)

    assert response.status_code == status.HTTP_200_OK
    assert response.headers['content-type'].startswith('text/event-stream')
    # 중간에서 저장하거나 모았다가 보내지 않게 한다
    assert response.headers['cache-control'] == 'no-cache'
    assert response.headers['x-accel-buffering'] == 'no'
    # 연결되자마자 주석 한 줄이 간다. 받는 쪽이 붙었다는 것을 안다
    assert response.text.startswith(': connected\n\n')


async def test_the_stream_of_an_ended_table_sends_everything_and_closes(client: AsyncClient, me: dict, friend: dict):
    table = await open_ended_table(client, me, friend)

    response = await client.get(stream_url(table), headers=friend)

    messages = parse(response)
    assert [(message['event'], message['id']) for message in messages] == [
        ('table_event', '1-0'),
        ('table_event', '2-0'),
        ('table_event', '3-0'),
        ('chat_message', '3-1'),
        ('closed', None),
    ]
    assert [message['data']['type'] for message in messages[:3]] == ['table_created', 'member_joined', 'table_ended']
    assert messages[3]['data']['content'] == HELLO
    assert messages[4]['data'] == {'reason': 'table_ended'}


async def test_the_data_has_the_same_shape_as_the_rest_api(client: AsyncClient, me: dict, friend: dict):
    table = await open_ended_table(client, me, friend)
    events = (await client.get(f'{TABLES_URL}/{table["id"]}/events', headers=friend)).json()['items']
    chat = (await client.get(f'{TABLES_URL}/{table["id"]}/messages', headers=friend)).json()['items']

    messages = parse(await client.get(stream_url(table), headers=friend))

    # 화면은 REST 로 읽은 것과 스트림으로 받은 것을 같은 코드로 다룬다
    assert [message['data'] for message in messages[:3]] == events
    assert messages[3]['data'] == chat[0]


async def test_starts_after_the_numbers_in_the_address(client: AsyncClient, me: dict, friend: dict):
    table = await open_ended_table(client, me, friend)

    response = await client.get(stream_url(table), params={'events_after': 2, 'messages_after': 1}, headers=friend)

    # REST 로 읽은 마지막 번호를 적고 붙으면 그 뒤의 것만 온다
    assert [(message['event'], message['id']) for message in parse(response)] == [
        ('table_event', '3-1'),
        ('closed', None),
    ]


async def test_resumes_after_the_last_event_id(client: AsyncClient, me: dict, friend: dict):
    table = await open_ended_table(client, me, friend)

    # 주소의 번호보다 머리말이 먼저다. 다시 붙는 쪽은 처음의 주소를 그대로 쓰기 때문이다
    response = await client.get(
        stream_url(table), params={'events_after': 0}, headers={**friend, 'Last-Event-ID': '3-0'}
    )

    assert [(message['event'], message['id']) for message in parse(response)] == [
        ('chat_message', '3-1'),
        ('closed', None),
    ]


async def test_gm_only_text_never_leaves(client: AsyncClient, me: dict, friend: dict):
    table = await open_ended_table(client, me, friend)

    response = await client.get(stream_url(table), headers=me)

    # 방장에게도 나가지 않는다
    assert GM_GUIDE not in response.text
    assert table['invite_code'] not in response.text
