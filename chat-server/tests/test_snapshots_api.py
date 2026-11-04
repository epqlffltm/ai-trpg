# chat-server/tests/test_snapshots_api.py

"""
장면 그림(#983)을 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 글과 그림의 모델은 가짜다.

보는 것.
  - 캐릭터의 답을 고르면 202(그리는 중), 다 그리면 asset 에 맡기고 확정한다. 목록에 ready 와 그림의 id 가 보인다
  - 지시는 지킬 것(전체이용가), 판의 인물, 서버의 시각, 그 답과 그 답이 답한 사람의 말로 만든다
  - 캐릭터의 그림을 참고 그림으로 넘기고 지시에 누구의 그림인지 적는다. 받지 못한 그림은 빼고 그린다.
    참고 그림을 받지 않는 provider 에는 받지도 넘기지도 않는다
  - 사람의 말은 422 not_drawable, 남의 말은 404, 남의 대화의 목록도 404 다
  - 한 대화에 그리는 중인 것은 하나다(둘째는 409, 홀드를 걸지 않는다). 끝나면 다시 그린다
  - 크레딧이 모자라면 402 이고 실패로 남는다. 공급자의 거절, asset 의 실패는 실패로 적고 돈을 돌려준다
  - 장면 그림을 만들지 않는 서버, 팔지 않는 가격표면 503 snapshot_unavailable 이다
  - 대화를 지우면 맡긴 그림을 asset 에서 지운다
  - 그리는 도중에 서버가 꺼진 것은 정리 작업이 실패로 적고 돌려준다
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from ai_core.fake import FakeImageProvider
from ai_core.image_provider import GeneratedImage, ImageRequest, ReferenceImage, ReferenceKind
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.snapshots.models import Snapshot
from app.snapshots.prompt import REFERENCE_RULE, RULES
from app.snapshots.providers import price_code_of
from app.snapshots.settler import SnapshotSettler
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MODEL = 'gemini-nano-banana-2.1'
PRICE_CODE = price_code_of(MODEL)
SNAPSHOT_PRICE = 160
START = 1000
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
# make_character 의 대표 그림
PORTRAIT = uuid.UUID('0b7c6f1e-2d3a-4b5c-8d9e-0f1a2b3c4d5e')
MESSAGES_URL = f'{API_PREFIX}/messages'


@dataclass
class SlowImageProvider:
    """hold 가 켜질 때까지 기다렸다가 그리는 그림 provider."""

    kind = 'slow'
    supports_references = True
    model: str = MODEL
    hold: asyncio.Event = field(default_factory=asyncio.Event)

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        await self.hold.wait()
        return GeneratedImage(data=b'png', mime_type='image/png', model=self.model)


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def billing(app: FastAPI) -> FakeBillingServer:
    server = FakeBillingServer(balances={ME: START})
    server.prices['chat.luna.i0.o0'] = 30
    server.prices[PRICE_CODE] = SNAPSHOT_PRICE
    app.state.billing = server.billing(server.make_client())
    return server


@pytest.fixture
def painter(app: FastAPI) -> FakeImageProvider:
    fake = FakeImageProvider(model=MODEL)
    app.state.image_provider = fake
    return fake


@pytest.fixture
async def answered(
    clean_tables: None,
    app: FastAPI,
    session: AsyncSession,
    client: AsyncClient,
    asset: FakeAsset,
    billing: FakeBillingServer,
    mine: dict,
) -> tuple[dict, str, str]:
    """대화 하나와 사람의 말 하나, 그 답 하나. (대화, 사람의 말 id, 답 id)"""
    app.state.model_router = FakeRouter(ScriptedProvider(pieces=['창밖에 비가 ', '내려요.']))
    await turn_on_luna(session)
    conversation = await start_with_luna(client, asset, mine)
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': '오늘 날씨 어때?'}, headers=mine)
    await asyncio.gather(*list(app.state.turns))
    events = parse_sse(response.text)
    return conversation, events[0][1]['user_message']['id'], events[-1][1]['message']['id']


async def draw(client: AsyncClient, headers: dict, message_id: str):
    return await client.post(f'{MESSAGES_URL}/{message_id}/snapshot', headers=headers)


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.snapshot_tasks))


async def listed(client: AsyncClient, headers: dict, conversation: dict) -> list[dict]:
    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/snapshots', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_an_answer_is_drawn_kept_and_charged(
    client: AsyncClient,
    app: FastAPI,
    answered: tuple,
    painter: FakeImageProvider,
    asset: FakeAsset,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation, _, answer_id = answered

    response = await draw(client, mine, answer_id)
    first = response.json()
    await finished(app)
    (snapshot,) = await listed(client, mine, conversation)

    assert (response.status_code, first['status'], first['message_id']) == (202, 'drawing', answer_id)
    assert (snapshot['status'], snapshot['code']) == ('ready', None)
    assert uuid.UUID(snapshot['image_id']) in asset.kept
    assert billing.holds[f'chat:img:{snapshot["id"]}'].status == 'captured'
    assert billing.balances[ME] == START - 30 - SNAPSHOT_PRICE
    (request,) = painter.calls
    assert request.prompt.startswith('\n'.join(RULES))
    assert '이름: 세라' in request.prompt and '시각: ' in request.prompt
    assert '사용자: 오늘 날씨 어때?' in request.prompt and '창밖에 비가 내려요.' in request.prompt
    # 대표 그림을 받으려 했지만 asset 에 없어(404) 빼고 그렸다
    assert request.references == () and '[참고 그림]' not in request.prompt
    assert any(call[:2] == ('fetch_image', PORTRAIT) for call in asset.calls)


async def test_the_character_image_is_passed_as_a_reference(
    client: AsyncClient, app: FastAPI, answered: tuple, painter: FakeImageProvider, asset: FakeAsset, mine: dict
):
    _, _, answer_id = answered
    asset.images[PORTRAIT] = b'portrait-png'

    await draw(client, mine, answer_id)
    await finished(app)

    (request,) = painter.calls
    portrait = ReferenceImage(data=b'portrait-png', mime_type='image/png', kind=ReferenceKind.CHARACTER)
    assert request.references == (portrait,)
    assert request.prompt.endswith(f'[참고 그림]\n1번째 그림: 세라\n{REFERENCE_RULE}')
    assert ('fetch_image', PORTRAIT, mine['Authorization'].removeprefix('Bearer ')) in asset.calls


async def test_a_provider_without_references_gets_none_and_nothing_is_fetched(
    client: AsyncClient, app: FastAPI, answered: tuple, painter: FakeImageProvider, asset: FakeAsset, mine: dict
):
    conversation, _, answer_id = answered
    asset.images[PORTRAIT] = b'portrait-png'
    painter.supports_references = False

    await draw(client, mine, answer_id)
    await finished(app)
    (snapshot,) = await listed(client, mine, conversation)

    (request,) = painter.calls
    assert (snapshot['status'], request.references) == ('ready', ())
    assert not any(call[0] == 'fetch_image' for call in asset.calls)


async def test_only_my_assistant_answers_are_drawn(
    client: AsyncClient,
    answered: tuple,
    painter: FakeImageProvider,
    billing: FakeBillingServer,
    mine: dict,
    signing_key: SigningKey,
):
    conversation, asked_id, answer_id = answered
    theirs = bearer(signing_key, SOMEONE_ELSE)

    own_words = await draw(client, mine, asked_id)
    someone_else = await draw(client, theirs, answer_id)
    their_list = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/snapshots', headers=theirs)

    assert (own_words.status_code, own_words.json()['code']) == (422, 'not_drawable')
    assert someone_else.status_code == their_list.status_code == status.HTTP_404_NOT_FOUND
    assert painter.calls == [] and not any(key.startswith('chat:img:') for key in billing.holds)


async def test_one_drawing_per_conversation(
    client: AsyncClient, app: FastAPI, answered: tuple, billing: FakeBillingServer, mine: dict
):
    conversation, _, answer_id = answered
    slow = SlowImageProvider()
    app.state.image_provider = slow

    first = await draw(client, mine, answer_id)
    second = await draw(client, mine, answer_id)
    slow.hold.set()
    await finished(app)
    again = await draw(client, mine, answer_id)
    await finished(app)

    assert (first.status_code, second.status_code, again.status_code) == (202, 409, 202)
    assert second.json()['code'] == 'snapshot_in_progress'
    assert [item['status'] for item in await listed(client, mine, conversation)] == ['ready', 'ready']
    assert len([key for key in billing.holds if key.startswith('chat:img:')]) == 2


async def test_short_credit_is_402_and_left_as_failed(
    client: AsyncClient, answered: tuple, painter: FakeImageProvider, billing: FakeBillingServer, mine: dict
):
    conversation, _, answer_id = answered
    billing.balances[ME] = 10

    response = await draw(client, mine, answer_id)

    assert (response.status_code, response.json()['code']) == (402, 'credit_short')
    assert [(item['status'], item['code']) for item in await listed(client, mine, conversation)] == [
        ('failed', 'credit_short')
    ]
    assert painter.calls == [] and billing.balances[ME] == 10


@pytest.mark.parametrize(
    ('refusal', 'asset_down', 'code'), [('refused', False, 'refused'), (None, True, 'asset_unavailable')]
)
async def test_failures_give_the_credit_back(
    client: AsyncClient,
    app: FastAPI,
    answered: tuple,
    painter: FakeImageProvider,
    asset: FakeAsset,
    billing: FakeBillingServer,
    mine: dict,
    refusal: str | None,
    asset_down: bool,
    code: str,
):
    conversation, _, answer_id = answered
    painter.error = refusal
    asset.down = asset_down
    before = billing.balances[ME]

    await draw(client, mine, answer_id)
    await finished(app)
    (snapshot,) = await listed(client, mine, conversation)

    assert (snapshot['status'], snapshot['code'], snapshot['image_id']) == ('failed', code, None)
    assert billing.holds[f'chat:img:{snapshot["id"]}'].status == 'released'
    assert billing.balances[ME] == before


async def test_without_a_provider_or_a_price_it_is_unavailable(
    client: AsyncClient, app: FastAPI, answered: tuple, billing: FakeBillingServer, mine: dict
):
    _, _, answer_id = answered
    app.state.image_provider = None
    off = await draw(client, mine, answer_id)
    app.state.image_provider = FakeImageProvider(model=MODEL)
    billing.not_for_sale.add(PRICE_CODE)
    not_sold = await draw(client, mine, answer_id)

    assert (off.status_code, off.json()['code']) == (503, 'snapshot_unavailable')
    assert (not_sold.status_code, not_sold.json()['code']) == (503, 'snapshot_unavailable')


async def test_deleting_the_conversation_discards_its_images(
    client: AsyncClient, app: FastAPI, answered: tuple, painter: FakeImageProvider, asset: FakeAsset, mine: dict
):
    conversation, _, answer_id = answered
    await draw(client, mine, answer_id)
    await finished(app)
    (snapshot,) = await listed(client, mine, conversation)

    response = await client.delete(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert asset.discarded == [uuid.UUID(snapshot['image_id'])] and not asset.kept


async def test_an_abandoned_drawing_is_released_by_the_settler(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    answered: tuple,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation, _, answer_id = answered
    slow = SlowImageProvider()
    app.state.image_provider = slow
    await draw(client, mine, answer_id)
    # 서버가 꺼진 채 남은 것처럼 그리는 일을 멈추지 않고 버린 뒤 오래전에 시작한 것으로 바꾼다
    for task in list(app.state.snapshot_tasks):
        app.state.snapshot_tasks.discard(task)
    long_ago = datetime.now(UTC) - timedelta(hours=1)
    await session.execute(update(Snapshot).values(created_at=long_ago))
    await session.commit()

    settled = await SnapshotSettler(app.state.session_factory, billing=lambda: app.state.billing).tick()
    (snapshot,) = await listed(client, mine, conversation)
    slow.hold.set()

    assert settled == 1
    assert (snapshot['status'], snapshot['code']) == ('failed', 'abandoned')
    assert billing.holds[f'chat:img:{snapshot["id"]}'].status == 'released'
