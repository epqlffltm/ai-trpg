# story-server/tests/test_actions_api.py

"""
행동(POST /conversations/{id}/actions)과 본 엔딩의 기록(GET /endings)을 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 이동: 행동 말(글과 그 뒤의 상태)이 붙고, 모델은 [행동] 을 붙인 글과 새 장소의 장면으로 답한다. 한 번 청구한다
  - 이벤트가 열리면 행동 말에 그 id 가 남고, 답은 그 장면 지시를 쓰고 그 장면이 부른 인물이 든다
  - 선택지를 고르면 그 효과가 상태에 든다
  - 건네면 물건이 줄고 호감도가 바뀐다. 행동 말에 엔진이 정한 반응(반가워했다)이 적힌다
  - 해금 대상인 장면(이벤트, 엔딩)이 열리면 갤러리에 그림과 장면의 인물이 남는다. 다시 열어도 하나다
  - 고백이 엔딩을 보면 행동 말에 엔딩이 남고 계정의 기록에 적힌다. 끝을 고른 세계관이면 그 뒤로 말과 행동을 받지 않는다.
    기록에 남지 않는 엔딩(unlock 이 거짓)은 적지 않는다
  - 할 수 없는 행동은 422 code 이고 아무것도 저장하지 않으며 차례를 놓는다. 모양이 틀린 행동은 입력 오류다
  - 세션 읽기의 상태는 가지의 끝의 상태다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message, MessageState
from app.turns.models import Generation
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.engine_worlds import condition, confession, effect, ending, event, gift, member
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

ENDINGS_URL = CONVERSATIONS_URL.replace('/conversations', '/endings')
GALLERY_URL = CONVERSATIONS_URL.replace('/conversations', '/gallery')
PICTURE = uuid.UUID('aaaaaaaa-1111-4222-8333-444444444444')
PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}]
# 해변에 가면 열리는 이벤트. 집에 사는 미나를 부르고 선택지 둘을 기다린다
SHELL = event(
    'shell',
    condition('reach_place', 'beach'),
    cast=['mina'],
    choices=[
        {'id': 'keep', 'text': '조개를 줍는다', 'effects': [effect('give_item', 'shell', 1)]},
        {'id': 'leave', 'text': '그냥 둔다', 'effects': []},
    ],
)


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


@pytest.fixture
def billing(app: FastAPI) -> FakeBillingServer:
    """가짜 결제 서버. 나는 크레딧 100 이 있고, luna 의 말 한 번은 30 이다."""
    server = FakeBillingServer(balances={ME: 100})
    server.prices[PRICE_CODE] = 30
    app.state.billing = server.billing(server.make_client())
    return server


@pytest.fixture
async def model_on(clean_tables: None, session: AsyncSession) -> None:
    await turn_on_luna(session)


async def start(client: AsyncClient, asset: FakeAsset, headers: dict, **fields) -> dict:
    """집과 해변이 길로 이어진 세계관으로 시작한다. fields 로 판의 칸을 덮어쓴다."""
    return await start_with_luna(client, asset, headers, {'paths': PATHS, **fields})


async def act(client: AsyncClient, headers: dict, conversation: dict, body: dict):
    return await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/actions', json=body, headers=headers)


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def detail(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


async def acted(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict, body: dict) -> list:
    response = await act(client, headers, conversation, body)
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)
    return parse_sse(response.text)


# --- 행동 ---


async def test_a_move_saves_the_action_and_its_state_then_answers(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation = await start(client, asset, mine)

    events = await acted(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})

    turn, done = events[0][1], events[-1][1]
    action = turn['user_message']
    assert (action['role'], action['content'], action['event_id'], action['ending_id']) == (
        'action',
        '해변(으)로 갔다. 지금은 1일째 아침.',
        None,
        None,
    )
    # 해변에는 준이 산다. 상태는 해변, 7시 30분이다
    assert (turn['cast'], turn['state']['place'], turn['state']['minutes'], turn['state']['day']) == (
        ['jun'],
        'beach',
        7 * 60 + 30,
        1,
    )
    assert done['message']['parent_id'] == action['id']
    messages, _ = router.provider.calls[0]
    assert messages[-1].content == '[행동] 해변(으)로 갔다. 지금은 1일째 아침.'
    assert '장소: 해변' in messages[0].content
    assert '@jun (준)' in messages[0].content
    # 상태는 행동 말에 붙었다. 한 번 청구했다
    saved = (await session.scalars(select(MessageState))).one()
    assert (saved.message_id, saved.state['place']) == (uuid.UUID(action['id']), 'beach')
    assert billing.balance(ME) == 70
    read = await detail(client, mine, conversation)
    assert [message['role'] for message in read['messages']] == ['action', 'assistant']
    assert (read['state']['place'], read['state']['cast']) == ('beach', ['jun'])


async def test_an_opened_event_directs_the_answer_and_its_choice_applies(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
):
    conversation = await start(client, asset, mine, events=[SHELL])

    moved = await acted(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})

    turn = moved[0][1]
    assert (turn['user_message']['event_id'], turn['state']['choosing']) == ('shell', 'shell')
    # 이벤트가 부른 미나가 해변의 준보다 앞서 장면에 든다. 답은 그 장면 지시를 쓴다
    assert turn['cast'] == ['mina', 'jun']
    assert '[장면 지시]\nshell 의 장면.' in router.provider.calls[0][0][0].content

    chose = await acted(app, client, mine, conversation, {'kind': 'choose', 'choice': 'keep'})

    turn = chose[0][1]
    assert turn['user_message']['content'] == '고른 것: 조개를 줍는다'
    assert (turn['state']['items'], turn['state']['choosing']) == ({'shell': 1}, None)
    # 고른 뒤에는 장면 지시가 없다
    assert '[장면 지시]' not in router.provider.calls[1][0][0].content


async def test_a_gift_hands_over_the_item_and_moves_affection(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    mina = {
        **member('mina', home='home', start=20, gifts=[gift('likes', 'flower', 10)]),
        'character': {'name': '미나'},
        'panel': ['affection'],
    }
    fields = {
        'cast': [mina],
        'items': [{'id': 'flower', 'name': '꽃'}],
        'start_items': [{'item': 'flower', 'count': 2}],
    }
    conversation = await start(client, asset, mine, **fields)

    events = await acted(app, client, mine, conversation, {'kind': 'give', 'cast': 'mina', 'item': 'flower'})

    turn = events[0][1]
    assert turn['user_message']['content'] == '미나에게 꽃을(를) 건넸다. 미나은(는) 반가워했다.'
    assert (turn['state']['items'], turn['state']['affection']['mina']) == ({'flower': 1}, 30)
    assert router.provider.calls[0][0][-1].content == '[행동] 미나에게 꽃을(를) 건넸다. 미나은(는) 반가워했다.'
    # 반응을 받으니 한 번 청구했다
    assert billing.balance(ME) == 70


async def test_a_collectible_scene_that_opens_is_kept_in_the_gallery(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
):
    sunset = event('sunset', condition('reach_place', 'beach'), cast=['mina'], repeat=True)
    sunset['scene'] |= {'image_id': str(PICTURE), 'collectible': True}
    # 지나가는 길의 이벤트는 그림이 있어도 해금 대상이 아니다
    plain = event('plain', condition('reach_place', 'home'), repeat=True)
    plain['scene'] |= {'image_id': str(uuid.uuid4())}
    conversation = await start(client, asset, mine, events=[sunset, plain])

    await acted(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})
    await acted(app, client, mine, conversation, {'kind': 'move', 'place': 'home'})
    # 다시 열려도 기록은 하나다
    again = await acted(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})
    assert again[0][1]['user_message']['event_id'] == 'sunset'

    world_id = (await detail(client, mine, conversation))['world']['id']
    items = (await client.get(GALLERY_URL, params={'world_id': world_id}, headers=mine)).json()['items']
    assert [(item['kind'], item['scene_id'], item['image_id'], item['cast']) for item in items] == [
        ('event', 'sunset', str(PICTURE), ['mina'])
    ]
    assert items[0]['conversation_id'] == conversation['id']


async def test_a_confession_that_ends_is_recorded_and_ends_the_session(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
):
    mina = {**member('mina', home='home', start=80, confession=confession('연인')), 'character': {'name': '미나'}}
    conversation = await start(
        client, asset, mine, cast=[mina], endings=[ending('with_mina', 'confess_success', 'mina')]
    )

    events = await acted(app, client, mine, conversation, {'kind': 'confess', 'cast': 'mina'})

    turn = events[0][1]
    assert turn['user_message']['content'] == '미나에게 고백했다. 미나은(는) 고백을 받아들였다.'
    assert (turn['user_message']['ending_id'], turn['state']['ending']) == ('with_mina', 'with_mina')
    assert '엔딩 「with_mina」에 닿았다.' in router.provider.calls[0][0][0].content
    # 계정의 기록에 남는다. 처음 본 세션도 적힌다
    world_id = (await detail(client, mine, conversation))['world']['id']
    records = (await client.get(ENDINGS_URL, params={'world_id': world_id}, headers=mine)).json()['items']
    assert [(record['ending_id'], record['conversation_id']) for record in records] == [
        ('with_mina', conversation['id'])
    ]
    # 끝을 고른 세계관이라 그 뒤로는 말도 행동도 받지 않는다
    talk = await client.post(
        f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json={'content': '그리고'}, headers=mine
    )
    again = await act(client, mine, conversation, {'kind': 'pass_time'})
    assert (talk.json()['code'], again.json()['code']) == ('session_ended', 'session_ended')


async def test_an_ending_that_is_not_unlocked_is_not_recorded(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
):
    conversation = await start(
        client,
        asset,
        mine,
        deadline_days=1,
        after_ending='epilogue',
        endings=[ending('solo', 'deadline', unlock=False)],
    )

    events = await acted(app, client, mine, conversation, {'kind': 'end_day'})

    assert events[0][1]['state']['ending'] == 'solo'
    world_id = (await detail(client, mine, conversation))['world']['id']
    records = (await client.get(ENDINGS_URL, params={'world_id': world_id}, headers=mine)).json()
    assert records == {'items': []}
    # 후일담이라 그 뒤로도 행동을 받는다
    assert (await act(client, mine, conversation, {'kind': 'pass_time'})).status_code == status.HTTP_200_OK
    await finished(app)


@pytest.mark.parametrize(
    ('body', 'code'),
    [
        ({'kind': 'move', 'place': 'home'}, 'cannot_move'),
        ({'kind': 'move', 'place': 'nowhere'}, 'cannot_move'),
        ({'kind': 'choose', 'choice': 'keep'}, 'no_choice'),
        ({'kind': 'confess', 'cast': 'jun'}, 'not_in_scene'),
        ({'kind': 'confess', 'cast': 'mina'}, 'not_confessable'),
        ({'kind': 'give', 'cast': 'jun', 'item': 'flower'}, 'not_in_scene'),
        ({'kind': 'give', 'cast': 'mina', 'item': 'flower'}, 'not_held'),
    ],
)
async def test_an_impossible_action_is_refused_and_saves_nothing(
    client: AsyncClient,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
    body: dict,
    code: str,
):
    conversation = await start(client, asset, mine)

    response = await act(client, mine, conversation, body)

    assert (response.status_code, response.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, code)
    assert router.provider.calls == []
    assert (await session.scalars(select(Message))).all() == []
    assert (await session.scalars(select(Generation))).all() == []
    session.expire_all()
    assert (await session.scalars(select(Conversation.generating_since))).one() is None


@pytest.mark.parametrize(
    'body',
    [
        {'kind': 'fly'},
        {'kind': 'move'},
        {'kind': 'move', 'place': ''},
        {'kind': 'pass_time', 'extra': 1},
        {'kind': 'give', 'cast': 'mina'},
    ],
)
async def test_a_malformed_action_is_an_input_error(
    client: AsyncClient, model_on: None, asset: FakeAsset, mine: dict, body: dict
):
    conversation = await start(client, asset, mine)

    response = await act(client, mine, conversation, body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'errors' in response.json()


async def test_endings_need_login(client: AsyncClient):
    response = await client.get(ENDINGS_URL, params={'world_id': str(uuid.uuid4())})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_endings_of_an_unknown_world_are_empty(client: AsyncClient, mine: dict):
    response = await client.get(ENDINGS_URL, params={'world_id': str(uuid.uuid4())}, headers=mine)

    assert response.json() == {'items': []}
