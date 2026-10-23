# chat-server/tests/test_world_api.py

"""
장소와 이동을 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 대화를 읽으면 가지 끝의 상태(장소, 흐른 시간, 소지품, 가 본 곳)가 실린다. 처음에는 판의 시작 상태다
  - 이동(POST /actions, kind move): 행동 말을 붙이고 상태를 바꾼 뒤 반응을 받는다. 한 번 청구한다.
    모델에는 [지금](장소, 갈 곳, 소지품)과 [행동] 이 간다
  - 갈 수 없으면 422(까닭이 code) 이고 아무것도 저장하지 않는다. 홀드가 거절되면 행동 말과 상태는 남는다
  - 상태는 가지를 따른다. 이동하기 전의 가지로 가면 그때의 장소다. 행동 말에 대한 반응도 다시 생성한다
  - 쓰기와 건네기: 소지품이 바뀌고 옷은 상대가 입는다. 건넬 때 덧붙인 한마디는 행동 말 아래의 사람의 말이고,
    반응은 그 한마디에 답한다(한 번 청구). 가지고 있지 않으면 422
  - 호감도: 판의 시작 값에서 행동의 규칙대로 바뀌고, 단계로 보이면 숫자를 내려보내지 않는다. 가지를 따른다
"""

import asyncio
import uuid

import pytest
from ai_core.provider import Role
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message
from app.main import API_PREFIX, STREAMS
from app.world.models import MessageState
from tests.assets import FakeAsset, make_character
from tests.billing import FakeBillingServer
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

WORLD = {
    'places': [
        {'id': 'library', 'name': '도서관', 'description': '책 냄새가 난다.', 'image_id': None},
        {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None},
        {'id': 'roof', 'name': '옥상', 'description': '', 'image_id': None},
    ],
    'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 15}, {'a': 'library', 'b': 'roof', 'minutes': 5}],
    'start_place': 'library',
    'items': [
        {'id': 'book', 'name': '시집', 'description': '', 'kind': 'thing', 'image_id': None},
        {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'image_id': None},
        {'id': 'cookie', 'name': '쿠키', 'description': '', 'kind': 'thing', 'consumable': True, 'image_id': None},
    ],
    'start_items': [{'item': 'book', 'count': 2}],
}
START = {
    'place': 'library',
    'minutes': 0,
    'inventory': [{'item': 'book', 'count': 2}],
    'visited': ['library'],
    'outfit': [],
    'affection': None,
}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['어서 와요.']))
    app.state.model_router = fake
    return fake


@pytest.fixture
def billing(app: FastAPI) -> FakeBillingServer:
    server = FakeBillingServer(balances={ME: 100})
    server.prices[PRICE_CODE] = 30
    app.state.billing = server.billing(server.make_client())
    return server


async def start(client: AsyncClient, asset: FakeAsset, headers: dict, world: dict | None) -> dict:
    character = asset.add_character(make_character(world=world))
    body = {'character_id': str(character.id), 'model': 'luna'}
    response = await client.post(CONVERSATIONS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    """지도와 물건이 있는 캐릭터와의 대화."""
    await turn_on_luna(session)
    return await start(client, asset, mine, WORLD)


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def move(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, place: str):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/actions'
    response = await client.post(url, json={'kind': 'move', 'place': place}, headers=headers)
    await finished(app)
    return response


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, body: dict):
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json=body, headers=headers)
    await finished(app)
    return parse_sse(response.text)


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


async def count_messages(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Message))


# --- 상태 ---


async def test_a_new_conversation_starts_where_the_version_says(conversation: dict):
    assert conversation['state'] == START
    assert conversation['character']['document']['places'][0]['id'] == 'library'


async def test_a_character_without_a_map_has_an_empty_state(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict, clean_tables: None
):
    await turn_on_luna(session)

    plain = await start(client, asset, mine, None)

    assert plain['state'] == {
        'place': None,
        'minutes': 0,
        'inventory': [],
        'visited': [],
        'outfit': [],
        'affection': None,
    }


# --- 이동 ---


async def test_moving_adds_an_action_changes_the_state_and_gets_a_reaction(
    client: AsyncClient,
    app: FastAPI,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    response = await move(client, app, mine, conversation, 'cafe')

    assert response.status_code == status.HTTP_200_OK
    events = parse_sse(response.text)
    action, done = events[0][1]['user_message'], events[-1][1]['message']
    assert (action['role'], action['content']) == ('action', '카페에 갔다. 15분이 걸렸다.')
    assert (done['parent_id'], done['content']) == (action['id'], '어서 와요.')
    detail = await read(client, mine, conversation)
    assert detail['state'] == {**START, 'place': 'cafe', 'minutes': 15, 'visited': ['library', 'cafe']}
    assert [message['role'] for message in detail['messages']] == ['assistant', 'action', 'assistant']
    # 반응을 받았으니 한 번 청구했다
    assert billing.balance(ME) == 70


async def test_the_model_reads_the_new_place_and_the_action(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    await move(client, app, mine, conversation, 'cafe')

    sent = router.provider.calls[0][0]
    card = sent[0].content
    assert '[지금]\n장소: 카페\n갈 수 있는 곳: 도서관(15분)\n사용자의 소지품: 시집 2개' in card
    assert (sent[-1].role, sent[-1].content) == (Role.USER, '[행동] 카페에 갔다. 15분이 걸렸다.')


async def test_talking_also_sends_the_scene(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    await say(client, app, mine, conversation, {'content': '안녕'})

    assert '장소: 도서관 — 책 냄새가 난다.' in router.provider.calls[0][0][0].content


@pytest.mark.parametrize(
    ('steps', 'place', 'code'),
    [
        ([], 'garden', 'place_not_found'),
        ([], 'library', 'already_there'),
        (['cafe'], 'roof', 'not_connected'),
    ],
)
async def test_places_that_cannot_be_reached_are_refused_and_nothing_is_saved(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    mine: dict,
    steps: list[str],
    place: str,
    code: str,
):
    for step in steps:
        await move(client, app, mine, conversation, step)
    before = await count_messages(session)

    response = await move(client, app, mine, conversation, place)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == code
    assert await count_messages(session) == before
    session.expire_all()
    row = await session.get(Conversation, uuid.UUID(conversation['id']))
    assert row.generating_since is None


async def test_a_character_without_a_map_cannot_move(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    await turn_on_luna(session)
    plain = await start(client, asset, mine, None)

    response = await move(client, app, mine, plain, 'cafe')

    assert (response.status_code, response.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'no_map')


async def test_a_refused_hold_keeps_the_move(
    client: AsyncClient,
    app: FastAPI,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    billing.balances[ME] = 10

    response = await move(client, app, mine, conversation, 'cafe')

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
    detail = await read(client, mine, conversation)
    assert detail['messages'][-1]['id'] == response.json()['message_id']
    assert detail['state']['place'] == 'cafe'
    assert router.provider.calls == []


@pytest.mark.parametrize(
    'body',
    [{'kind': 'fly', 'place': 'cafe'}, {'kind': 'move', 'place': '카페'}, {'kind': 'move'}, {'place': 'cafe'}],
)
async def test_a_malformed_action_is_refused(client: AsyncClient, conversation: dict, mine: dict, body: dict):
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/actions', json=body, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 가지 ---


async def test_the_state_follows_the_branch(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    first = (await say(client, app, mine, conversation, {'content': '안녕'}))[0][1]['user_message']
    await move(client, app, mine, conversation, 'cafe')

    # 이동하기 전의 말을 고쳐 새 가지로 가면 그때의 장소다
    await say(client, app, mine, conversation, {'content': '반가워', 'edit_of': first['id']})

    assert (await read(client, mine, conversation))['state'] == START


async def test_the_reaction_to_a_move_can_be_regenerated(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    reaction = parse_sse((await move(client, app, mine, conversation, 'cafe')).text)[-1][1]['message']
    router.provider = ScriptedProvider(pieces=['다시 와요.'])

    response = await client.post(f'{API_PREFIX}/messages/{reaction["id"]}/regenerate', headers=mine)
    await finished(app)

    again = parse_sse(response.text)[-1][1]['message']
    assert (again['parent_id'], again['content']) == (reaction['parent_id'], '다시 와요.')
    assert (await read(client, mine, conversation))['state']['place'] == 'cafe'


async def test_a_move_left_without_a_reaction_gets_one(
    client: AsyncClient,
    app: FastAPI,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    billing.balances[ME] = 10
    action_id = (await move(client, app, mine, conversation, 'cafe')).json()['message_id']
    billing.balances[ME] = 100

    response = await client.post(f'{API_PREFIX}/messages/{action_id}/regenerate', headers=mine)
    await finished(app)

    # 반응을 못 받은 행동 말에 반응을 쓴다(답을 못 받은 사람의 말과 같다)
    assert parse_sse(response.text)[-1][1]['message']['parent_id'] == action_id


def test_the_action_address_is_a_stream():
    assert STREAMS.matches(f'{CONVERSATIONS_URL}/{uuid.uuid4()}/actions')


# --- 물건 ---


async def act(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, body: dict):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/actions'
    response = await client.post(url, json=body, headers=headers)
    await finished(app)
    return response


@pytest.fixture
async def stocked(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    """목도리 하나와 쿠키 하나를 가지고 시작하는 대화."""
    await turn_on_luna(session)
    world = {**WORLD, 'start_items': [{'item': 'scarf', 'count': 1}, {'item': 'cookie', 'count': 1}]}
    return await start(client, asset, mine, world)


async def test_using_a_consumable_takes_it_and_gets_a_reaction(
    client: AsyncClient, app: FastAPI, stocked: dict, router: FakeRouter, mine: dict
):
    response = await act(client, app, mine, stocked, {'kind': 'use', 'item': 'cookie'})

    events = parse_sse(response.text)
    assert (events[0][1]['user_message']['content'], events[-1][0]) == ('쿠키를 썼다.', 'done')
    state = (await read(client, mine, stocked))['state']
    assert state['inventory'] == [{'item': 'scarf', 'count': 1}]


async def test_giving_clothes_with_words_puts_them_on_and_answers_the_words(
    client: AsyncClient,
    app: FastAPI,
    stocked: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    body = {'kind': 'give', 'item': 'scarf', 'words': '추우니까 해.'}

    response = await act(client, app, mine, stocked, body)

    turn = parse_sse(response.text)[0][1]
    action, words = turn['action'], turn['user_message']
    assert (action['role'], action['content']) == ('action', '목도리를 건넸다.')
    assert (words['role'], words['content'], words['parent_id']) == ('user', '추우니까 해.', action['id'])
    detail = await read(client, mine, stocked)
    assert [message['role'] for message in detail['messages']] == ['assistant', 'action', 'user', 'assistant']
    assert detail['messages'][-1]['parent_id'] == words['id']
    assert (detail['state']['outfit'], detail['state']['inventory']) == (['scarf'], [{'item': 'cookie', 'count': 1}])
    # 행동과 말을 한 턴에 붙였으니 반응은 한 번이고 청구도 한 번이다
    assert billing.balance(ME) == 70
    sent = router.provider.calls[0][0]
    assert [message.content for message in sent[-2:]] == ['[행동] 목도리를 건넸다.', '추우니까 해.']
    assert '상대의 차림: 목도리' in sent[0].content


async def test_giving_without_words_answers_the_action(
    client: AsyncClient, app: FastAPI, stocked: dict, router: FakeRouter, mine: dict
):
    turn = parse_sse((await act(client, app, mine, stocked, {'kind': 'give', 'item': 'cookie'})).text)[0][1]

    assert (turn['user_message']['role'], turn['action']) == ('action', None)


async def test_a_refused_gift_with_words_keeps_both(
    client: AsyncClient,
    app: FastAPI,
    stocked: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    billing.balances[ME] = 10

    response = await act(client, app, mine, stocked, {'kind': 'give', 'item': 'scarf', 'words': '받아.'})

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
    detail = await read(client, mine, stocked)
    # 가지의 끝은 한마디다(행동 말과 같은 때에 생겼어도 한마디가 뒤다)
    assert [message['content'] for message in detail['messages'][-2:]] == ['목도리를 건넸다.', '받아.']
    assert detail['messages'][-1]['id'] == response.json()['message_id']
    branch = await client.put(
        f'{CONVERSATIONS_URL}/{stocked["id"]}/branch', json={'message_id': detail['messages'][-2]['id']}, headers=mine
    )
    assert branch.json()['messages'][-1]['content'] == '받아.'


@pytest.mark.parametrize(
    ('body', 'code'),
    [
        ({'kind': 'use', 'item': 'book'}, 'not_held'),
        ({'kind': 'give', 'item': 'sword'}, 'item_not_found'),
    ],
)
async def test_items_not_held_are_refused(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    stocked: dict,
    router: FakeRouter,
    mine: dict,
    body: dict,
    code: str,
):
    before = await count_messages(session)

    response = await act(client, app, mine, stocked, body)

    assert (response.status_code, response.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, code)
    assert await count_messages(session) == before


@pytest.mark.parametrize(
    'body',
    [
        {'kind': 'give', 'item': 'scarf', 'words': '  '},
        {'kind': 'give', 'item': 'scarf', 'words': 'x' * 4001},
        {'kind': 'use', 'item': 'scarf', 'words': '먹어'},
    ],
)
async def test_malformed_item_actions_are_refused(client: AsyncClient, stocked: dict, mine: dict, body: dict):
    response = await client.post(f'{CONVERSATIONS_URL}/{stocked["id"]}/actions', json=body, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 호감도 ---

AFFECTION = {
    'display': 'stage',
    'start': 25,
    'stages': [{'name': '낯섦', 'at': 0}, {'name': '친구', 'at': 30}],
    'rules': [
        {'id': 'date', 'on': {'kind': 'reach_place', 'target': 'cafe'}, 'change': 10, 'once': True},
        {'id': 'gift', 'on': {'kind': 'give_item', 'target': 'scarf'}, 'change': 3, 'once': False},
    ],
}


@pytest.fixture
async def liked(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    """호감도가 있는 캐릭터와의 대화. 단계 이름으로 보인다."""
    await turn_on_luna(session)
    return await start(client, asset, mine, {**WORLD, 'affection': AFFECTION})


async def test_affection_starts_from_the_version_and_hides_the_number(liked: dict):
    assert liked['state']['affection'] == {
        'display': 'stage',
        'value': None,
        'stage': '낯섦',
        'stage_index': 0,
        'stages': 2,
    }


async def test_a_first_date_raises_affection_once(
    client: AsyncClient, app: FastAPI, session: AsyncSession, liked: dict, router: FakeRouter, mine: dict
):
    await move(client, app, mine, liked, 'cafe')
    await move(client, app, mine, liked, 'library')
    await move(client, app, mine, liked, 'cafe')

    state = (await read(client, mine, liked))['state']
    assert state['affection']['stage'] == '친구'
    # 숫자는 내려보내지 않지만 서버는 35 를 쥐고 있다(한 번만 올랐다)
    rows = (await session.execute(select(MessageState.affection))).scalars().all()
    assert sorted(rows) == [35, 35, 35]
    assert '사용자에 대한 호감: 친구' in router.provider.calls[-1][0][0].content


async def test_affection_follows_the_branch(
    client: AsyncClient, app: FastAPI, liked: dict, router: FakeRouter, mine: dict
):
    first = (await say(client, app, mine, liked, {'content': '안녕'}))[0][1]['user_message']
    await move(client, app, mine, liked, 'cafe')

    await say(client, app, mine, liked, {'content': '다시', 'edit_of': first['id']})

    assert (await read(client, mine, liked))['state']['affection']['stage'] == '낯섦'


async def test_a_state_written_before_affection_reads_as_the_start(
    client: AsyncClient, app: FastAPI, session: AsyncSession, liked: dict, router: FakeRouter, mine: dict
):
    await move(client, app, mine, liked, 'cafe')
    # 호감도를 더하기 전에 적힌 상태와 같게 만든다
    await session.execute(update(MessageState).values(affection=None))
    await session.commit()

    assert (await read(client, mine, liked))['state']['affection']['stage'] == '낯섦'
