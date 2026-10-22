# chat-server/tests/test_continue_api.py

"""
이어서 출력(POST /api/v1/chat/messages/{id}/continue)을 API 로 검증한다. 실제 DB(chat_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 끊긴 답 끝에 이어 붙인다. 같은 말(id)이고, 다 쓰면 complete 와 선택지, 또 끊기면 partial 이다
  - 모델이 되풀이한 앞부분은 흘리지도 저장하지도 않는다. 모델에는 끊긴 답까지와 끝의 지시가 간다
  - 새 호출이라 새로 청구한다. 글 없이 실패하거나 거절되면 끊긴 답은 그대로다
  - 끊긴 답이 아니거나(다 쓴 답, 사람의 말, 인사말) 지금 가지의 끝이 아니면 422. 남의 말은 404, 답을 쓰는 중이면 409
  - 사람이 멈추면 받은 만큼 붙인다
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from ai_core.provider import ProviderError, Role
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversation.continuation import instruction
from app.conversations.models import Conversation
from app.main import API_PREFIX, STREAMS
from app.turns import repository
from app.turns.models import Generation
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
# 길이 상한에서 끊긴 답
CUT = '그녀는 문을 열고 안으로 천천히 걸어'
# 모델이 끝을 되풀이하며 이어 쓴 글과 선택지
GOES_ON = ['안으로 천천히 걸어', ' 들어갔다.\n<suggestions>\n따라 들어간다\n']


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    """처음의 답은 길이 상한에서 끊긴다."""
    fake = FakeRouter(ScriptedProvider(pieces=[CUT], truncated=True))
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
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str = '안녕') -> list:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    await finished(app)
    assert response.status_code == status.HTTP_200_OK, response.text
    return parse_sse(response.text)


async def cut_answer(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict) -> dict:
    """끊긴 답(partial) 하나를 만든다."""
    done = (await say(client, app, headers, conversation))[-1][1]['message']
    assert done['status'] == 'partial'
    return done


async def go_on(client: AsyncClient, headers: dict, message_id: str):
    return await client.post(f'{API_PREFIX}/messages/{message_id}/continue', headers=headers)


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


async def test_the_cut_answer_is_continued_in_place(
    client: AsyncClient,
    app: FastAPI,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    cut = await cut_answer(client, app, mine, conversation)
    router.provider = ScriptedProvider(pieces=GOES_ON)

    response = await go_on(client, mine, cut['id'])
    await finished(app)

    assert response.status_code == status.HTTP_200_OK
    events = parse_sse(response.text)
    turn, done = events[0][1], events[-1][1]['message']
    assert (turn['continues'], turn['user_message']['id']) == (cut['id'], cut['parent_id'])
    # 되풀이한 앞부분과 선택지는 흘리지 않았다
    assert ''.join(data['text'] for event, data in events if event == 'delta') == ' 들어갔다.\n'
    assert (done['id'], done['content'], done['status']) == (cut['id'], f'{CUT} 들어갔다.', 'complete')
    assert done['suggestions'] == ['따라 들어간다']
    detail = await read(client, mine, conversation)
    assert detail['messages'][-1]['content'] == f'{CUT} 들어갔다.'
    assert detail['messages'][-1]['suggestions'] == ['따라 들어간다']
    assert len(detail['messages']) == 3
    # 새 호출이라 새로 청구했다
    assert billing.balance(ME) == 40


async def test_the_model_gets_the_cut_answer_and_the_instruction(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    cut = await cut_answer(client, app, mine, conversation)
    provider = ScriptedProvider(pieces=GOES_ON)
    router.provider = provider

    await go_on(client, mine, cut['id'])
    await finished(app)

    sent = provider.calls[0][0]
    assert [(message.role, message.content) for message in sent[-2:]] == [
        (Role.ASSISTANT, CUT),
        (Role.USER, instruction()),
    ]


async def test_an_answer_cut_again_can_be_continued_again(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    cut = await cut_answer(client, app, mine, conversation)
    router.provider = ScriptedProvider(pieces=[' 들어'], truncated=True)
    first = parse_sse((await go_on(client, mine, cut['id'])).text)[-1][1]['message']
    await finished(app)
    router.provider = ScriptedProvider(pieces=['갔다.'])

    second = parse_sse((await go_on(client, mine, cut['id'])).text)[-1][1]['message']
    await finished(app)

    assert (first['status'], first['suggestions']) == ('partial', [])
    assert (second['content'], second['status']) == (f'{CUT} 들어갔다.', 'complete')


async def test_a_failure_before_any_text_leaves_the_cut_answer_alone(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    cut = await cut_answer(client, app, mine, conversation)
    router.provider = ScriptedProvider(pieces=[], error=ProviderError('timeout'))

    response = await go_on(client, mine, cut['id'])
    await finished(app)

    assert parse_sse(response.text)[-1] == ('failed', {'code': 'timeout'})
    last = (await read(client, mine, conversation))['messages'][-1]
    assert (last['content'], last['status']) == (CUT, 'partial')
    generation = (await session.scalars(select(Generation).order_by(Generation.created_at.desc()))).first()
    assert (generation.billing_status, generation.message_id) == ('released', None)
    assert billing.balance(ME) == 70


async def test_a_refused_continuation_leaves_everything_alone(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    cut = await cut_answer(client, app, mine, conversation)
    billing.balances[ME] = 10

    response = await go_on(client, mine, cut['id'])

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
    assert response.json()['message_id'] == cut['parent_id']
    session.expire_all()
    row = await session.get(Conversation, uuid.UUID(conversation['id']))
    assert (str(row.active_leaf_id), row.generating_since) == (cut['id'], None)


@pytest.mark.parametrize('which', ['complete', 'user', 'greeting'])
async def test_only_a_cut_answer_can_be_continued(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict, which: str
):
    router.provider = ScriptedProvider()
    done = (await say(client, app, mine, conversation))[-1][1]['message']
    message_id = {
        'complete': done['id'],
        'user': done['parent_id'],
        'greeting': conversation['messages'][0]['id'],
    }[which]
    calls = len(router.provider.calls)

    response = await go_on(client, mine, message_id)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'not_continuable'
    assert len(router.provider.calls) == calls


async def test_a_cut_answer_that_is_not_the_end_of_the_branch_is_422(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    cut = await cut_answer(client, app, mine, conversation)
    router.provider = ScriptedProvider()
    await say(client, app, mine, conversation, '그다음')

    response = await go_on(client, mine, cut['id'])

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'not_continuable'
    # 잡았던 차례는 놓았다
    session.expire_all()
    row = await session.get(Conversation, uuid.UUID(conversation['id']))
    assert row.generating_since is None


@pytest.mark.parametrize('who', ['theirs', 'nobody'])
async def test_someone_elses_or_a_missing_message_is_404(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict, theirs: dict, who: str
):
    cut = await cut_answer(client, app, mine, conversation)
    headers, message_id = (theirs, cut['id']) if who == 'theirs' else (mine, str(uuid.uuid4()))

    response = await go_on(client, headers, message_id)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['code'] == 'message_not_found'


async def test_continuing_while_answering_is_409(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    cut = await cut_answer(client, app, mine, conversation)
    await session.execute(
        update(Conversation)
        .where(Conversation.id == uuid.UUID(conversation['id']))
        .values(generating_since=datetime.now(UTC))
    )
    await session.commit()

    response = await go_on(client, mine, cut['id'])

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['code'] == 'generation_in_progress'


async def test_a_stopped_continuation_keeps_what_it_got(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    cut = await cut_answer(client, app, mine, conversation)
    router.provider = ScriptedProvider(pieces=[' 들어'], hold=asyncio.Event())
    going = asyncio.create_task(go_on(client, mine, cut['id']))
    while not router.provider.calls:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)
    generation = (await session.scalars(select(Generation).where(Generation.billing_status == 'held'))).one()

    await client.post(f'{API_PREFIX}/generations/{generation.id}/stop', headers=mine)
    response = await going
    await finished(app)

    done = parse_sse(response.text)[-1][1]['message']
    assert (done['content'], done['status']) == (f'{CUT} 들어', 'partial')


async def test_text_held_while_it_matched_is_still_streamed(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    cut = await cut_answer(client, app, mine, conversation)
    # "천천히" 는 끊긴 답 끝의 일부와 같아 끝까지 붙잡혔다. 짧아서 겹친 것으로 보지 않고 흘린다
    router.provider = ScriptedProvider(pieces=['천천히'])

    events = parse_sse((await go_on(client, mine, cut['id'])).text)
    await finished(app)

    assert ''.join(data['text'] for event, data in events if event == 'delta') == '천천히'
    assert events[-1][1]['message']['content'] == f'{CUT}천천히'


async def test_a_branch_changed_before_the_lock_is_seen(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    mine: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    cut = await cut_answer(client, app, mine, conversation)
    original = repository.lock_turn

    async def moved_first(locking: AsyncSession, conversation_id, now, stale):
        # 대화를 읽은 뒤 차례를 잡기 전에 다른 요청이 가지를 바꿨다
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(active_leaf_id=uuid.UUID(cut['parent_id']))
        )
        await session.commit()
        return await original(locking, conversation_id, now, stale)

    monkeypatch.setattr(repository, 'lock_turn', moved_first)

    response = await go_on(client, mine, cut['id'])

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_the_continue_address_is_a_stream():
    assert STREAMS.matches(f'{API_PREFIX}/messages/{uuid.uuid4()}/continue')
