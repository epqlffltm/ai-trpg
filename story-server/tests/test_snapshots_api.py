# story-server/tests/test_snapshots_api.py

"""
장면 그림(#983)을 API 로 검증한다. 실제 DB(story_test)에서 돈다. asset 서버, 결제 서버, 글과 그림의 모델은 가짜다.

보는 것.
  - 모델의 답을 고르면 202(그리는 중), 다 그리면 asset 에 맡기고 확정한다. 목록에 ready 와 그림의 id 가 보인다
  - 지시는 지킬 것(전체이용가), 세계관, 엔진의 때와 장소, 장면의 인물, 그 답의 말 조각과 사람의 말로 만든다
  - 장면의 인물의 그림(기본 표정, 없으면 대표 그림)을 참고 그림으로 넘기고 지시에 누구의 그림인지 적는다.
    받지 못한 그림은 빼고 그린다. 그림이 없는 인물은 받지 않는다
  - 사람의 말은 422 not_drawable, 남의 말은 404, 남의 세션의 목록도 404 다
  - 한 세션에 그리는 중인 것은 하나다(둘째는 409, 홀드를 걸지 않는다). 끝나면 다시 그린다
  - 크레딧이 모자라면 402 이고 실패로 남는다. 공급자의 거절, asset 의 실패는 실패로 적고 돈을 돌려준다
  - 장면 그림을 만들지 않는 서버, 팔지 않는 가격표면 503 snapshot_unavailable 이다
  - 세션을 지우면 맡긴 그림을 asset 에서 지운다
  - 그리는 도중에 서버가 꺼진 것은 정리 작업이 실패로 적고 돌려준다
  - 내 그림들(갤러리)은 다 그린 것만 최근 것부터다. 남의 것, 지운 대화의 것은 보이지 않는다
  - 내 그림 한 장을 지우면 asset 의 그림까지 지운다. 그리는 중이나 청구를 정리하는 중이면 409, 남의 것은 404.
    asset 이 안 되면 503 이고 기록은 남는다
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
from app.turns.models import BillingStatus
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, WORLD_FIELDS, bearer, parse_sse, start_with_luna, turn_on_luna
from tests.turns import PRICE_CODE as TURN_PRICE

pytestmark = pytest.mark.usefixtures('clean_tables')

MODEL = 'gemini-nano-banana-2.1'
PRICE_CODE = price_code_of(MODEL)
SNAPSHOT_PRICE = 160
START = 1000
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
MESSAGES_URL = f'{API_PREFIX}/messages'
KEPT_URL = f'{API_PREFIX}/snapshots'
# 미나의 대표 그림과 기본 표정의 그림
PORTRAIT = uuid.UUID('7a1d2c3b-4e5f-4a6b-8c7d-9e0f1a2b3c4d')
SPRITE = uuid.UUID('7a1d2c3b-4e5f-4a6b-8c7d-9e0f1a2b3c4e')


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
    server.prices[TURN_PRICE] = 30
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
    """세션 하나와 사람의 말 하나, 그 답 하나. (세션, 사람의 말 id, 답 id). 답은 서술 한 줄과 미나의 말이다"""
    return await answer_once(app, session, client, asset, mine)


async def answer_once(
    app: FastAPI, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict, fields: dict | None = None
) -> tuple[dict, str, str]:
    """luna 로 세션을 시작하고 한 번 묻는다. fields 로 판의 칸을 덮어쓴다."""
    app.state.model_router = FakeRouter()
    await turn_on_luna(session)
    conversation = await start_with_luna(client, asset, mine, fields)
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
    assert billing.holds[f'story:img:{snapshot["id"]}'].status == 'captured'
    assert billing.balances[ME] == START - 30 - SNAPSHOT_PRICE
    (request,) = painter.calls
    # 미나에게 그림이 없어 받지 않는다
    assert request.references == () and asset.fetched == [] and '[참고 그림]' not in request.prompt
    assert request.prompt.startswith('\n'.join(RULES))
    assert '[세계관]\n이름: 여름 마을' in request.prompt and '때: 1일째 ' in request.prompt
    assert '장면의 인물:\n- 미나' in request.prompt
    assert '사용자: 오늘 날씨 어때?\n바람이 분다.\n미나: 왔구나.' in request.prompt


def mina_with(character: dict) -> dict:
    """미나의 캐릭터 칸을 바꾼 판의 칸."""
    mina, jun = WORLD_FIELDS['cast']
    return {'cast': [{**mina, 'character': {'name': '미나', **character}}, jun]}


async def test_the_cast_image_is_passed_as_a_reference(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    painter: FakeImageProvider,
    asset: FakeAsset,
    billing: FakeBillingServer,
    mine: dict,
):
    smile = {'id': 'smile', 'image_id': str(PORTRAIT), 'expression': '웃음'}
    sprites = [smile, {'id': 'base', 'image_id': str(SPRITE)}]
    fields = mina_with({'image_id': str(PORTRAIT), 'sprites': sprites})
    _, _, answer_id = await answer_once(app, session, client, asset, mine, fields)
    asset.images[SPRITE] = b'mina-png'

    await draw(client, mine, answer_id)
    await finished(app)

    (request,) = painter.calls
    assert asset.fetched == [SPRITE]
    mina = ReferenceImage(data=b'mina-png', mime_type='image/png', kind=ReferenceKind.CHARACTER)
    assert request.references == (mina,)
    assert request.prompt.endswith(f'[참고 그림]\n1번째 그림: 미나\n{REFERENCE_RULE}')


async def test_a_missing_reference_is_left_out(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    painter: FakeImageProvider,
    asset: FakeAsset,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation, _, answer_id = await answer_once(
        app, session, client, asset, mine, mina_with({'image_id': str(PORTRAIT)})
    )

    await draw(client, mine, answer_id)
    await finished(app)
    (snapshot,) = await listed(client, mine, conversation)

    (request,) = painter.calls
    assert (snapshot['status'], asset.fetched, request.references) == ('ready', [PORTRAIT], ())
    assert '[참고 그림]' not in request.prompt


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
    assert painter.calls == [] and not any(key.startswith('story:img:') for key in billing.holds)


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
    assert len([key for key in billing.holds if key.startswith('story:img:')]) == 2


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
    assert billing.holds[f'story:img:{snapshot["id"]}'].status == 'released'
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


async def test_deleting_the_session_discards_its_images(
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
    assert billing.holds[f'story:img:{snapshot["id"]}'].status == 'released'


async def test_my_gallery_lists_the_ready_ones_newest_first(
    client: AsyncClient,
    app: FastAPI,
    answered: tuple,
    painter: FakeImageProvider,
    mine: dict,
    signing_key: SigningKey,
):
    conversation, _, answer_id = answered
    for error in (None, 'refused', None):
        painter.error = error
        await draw(client, mine, answer_id)
        await finished(app)
    ready = [item for item in await listed(client, mine, conversation) if item['status'] == 'ready']

    page = await client.get(KEPT_URL, headers=mine)
    second = await client.get(KEPT_URL, params={'limit': 1, 'offset': 1}, headers=mine)
    theirs = await client.get(KEPT_URL, headers=bearer(signing_key, SOMEONE_ELSE))
    await client.delete(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)
    after_delete = await client.get(KEPT_URL, headers=mine)

    assert page.status_code == status.HTTP_200_OK, page.text
    body = page.json()
    assert body['total'] == 2 and [item['id'] for item in body['items']] == [ready[1]['id'], ready[0]['id']]
    first = body['items'][0]
    assert (first['image_id'], first['conversation_id'], first['message_id']) == (
        ready[1]['image_id'],
        conversation['id'],
        answer_id,
    )
    assert (first['conversation_title'], first['work_name']) == (conversation['title'], '여름 마을')
    assert [item['id'] for item in second.json()['items']] == [ready[0]['id']]
    assert theirs.json() == after_delete.json() == {'items': [], 'total': 0}


async def remove(client: AsyncClient, headers: dict, snapshot_id: str):
    return await client.delete(f'{KEPT_URL}/{snapshot_id}', headers=headers)


async def test_deleting_a_snapshot_discards_its_image(
    client: AsyncClient,
    app: FastAPI,
    answered: tuple,
    painter: FakeImageProvider,
    asset: FakeAsset,
    billing: FakeBillingServer,
    mine: dict,
    signing_key: SigningKey,
):
    conversation, _, answer_id = answered
    await draw(client, mine, answer_id)
    await finished(app)
    (snapshot,) = await listed(client, mine, conversation)

    theirs = await remove(client, bearer(signing_key, SOMEONE_ELSE), snapshot['id'])
    missing = await remove(client, mine, str(uuid.uuid4()))
    response = await remove(client, mine, snapshot['id'])
    again = await remove(client, mine, snapshot['id'])

    assert theirs.status_code == missing.status_code == again.status_code == status.HTTP_404_NOT_FOUND
    assert again.json()['code'] == 'snapshot_not_found'
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert asset.discarded == [uuid.UUID(snapshot['image_id'])]
    assert await listed(client, mine, conversation) == []
    assert (await client.get(KEPT_URL, headers=mine)).json()['total'] == 0
    assert billing.holds[f'story:img:{snapshot["id"]}'].status == 'captured'


async def test_a_drawing_or_settling_snapshot_is_not_deleted(
    client: AsyncClient, app: FastAPI, session: AsyncSession, answered: tuple, mine: dict
):
    conversation, _, answer_id = answered
    slow = SlowImageProvider()
    app.state.image_provider = slow
    await draw(client, mine, answer_id)
    (drawing,) = await listed(client, mine, conversation)

    busy = await remove(client, mine, drawing['id'])
    slow.hold.set()
    await finished(app)
    await session.execute(update(Snapshot).values(billing_status=BillingStatus.CAPTURE_DUE))
    await session.commit()
    settling = await remove(client, mine, drawing['id'])

    assert (busy.status_code, busy.json()['code']) == (409, 'snapshot_in_progress')
    assert (settling.status_code, settling.json()['code']) == (409, 'snapshot_settling')
    assert len(await listed(client, mine, conversation)) == 1


async def test_when_asset_is_down_the_record_stays_for_another_try(
    client: AsyncClient, app: FastAPI, answered: tuple, painter: FakeImageProvider, asset: FakeAsset, mine: dict
):
    conversation, _, answer_id = answered
    await draw(client, mine, answer_id)
    await finished(app)
    (snapshot,) = await listed(client, mine, conversation)

    asset.down = True
    down = await remove(client, mine, snapshot['id'])
    kept = await listed(client, mine, conversation)
    asset.down = False
    retried = await remove(client, mine, snapshot['id'])

    assert (down.status_code, down.json()['code']) == (503, 'asset_unavailable')
    assert [item['id'] for item in kept] == [snapshot['id']]
    assert retried.status_code == status.HTTP_204_NO_CONTENT


async def test_a_failed_snapshot_is_deleted_without_asset(
    client: AsyncClient,
    answered: tuple,
    painter: FakeImageProvider,
    asset: FakeAsset,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation, _, answer_id = answered
    billing.balances[ME] = 10
    await draw(client, mine, answer_id)
    (failed,) = await listed(client, mine, conversation)

    response = await remove(client, mine, failed['id'])

    assert (failed['status'], response.status_code) == ('failed', status.HTTP_204_NO_CONTENT)
    assert asset.discarded == [] and await listed(client, mine, conversation) == []
