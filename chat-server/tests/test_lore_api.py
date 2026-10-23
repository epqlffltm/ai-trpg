# chat-server/tests/test_lore_api.py

"""
로어북을 뜻으로 찾는 일(#672, app/lore/)을 API 로 검증한다. 실제 DB(chat_test)와 pgvector 에서 돈다.
임베딩 모델은 가짜(낱말이 겹치면 가깝다)다.
asset 서버, 결제 서버, 대화 모델도 가짜다.

보는 것.
  - 대화를 시작하면 판의 사본의 항목을 벡터로 바꿔 둔다. 다시 해도 줄이 늘지 않는다
  - 키워드가 맞지 않아도 뜻이 가까운 항목이 카드의 "[로어북]" 에 들어간다(키워드로 고른 것 뒤).
    먼 항목은 들어가지 않는다
  - 뜻으로 찾기를 끄면(EMBEDDER=off) 상시와 키워드만이다
  - 찾다가 실패하면 상시와 키워드로 답한다. 벡터가 없으면 그때 만들기를 맡긴다
  - 사본을 지우면 벡터도 지워진다
"""

import asyncio
import uuid

import pytest
from ai_core.fake import FakeEmbedder
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.schemas import CharacterCopy
from app.conversations.models import Conversation, ImportedCharacter
from app.lore.indexing import LoreIndexer
from app.lore.models import LoreEmbedding
from app.lore.recall import LoreRecall
from tests.assets import FakeAsset, make_character
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

TOWER = {
    'id': 'tower',
    'name': '붉은 탑',
    'kind': 'place',
    'keywords': ['마탑'],
    'content': '붉은 탑 꼭대기에 별을 보는 방이 있다.',
    'constant': False,
}
RIVER = {'id': 'river', 'name': '은빛 강', 'kind': 'place', 'keywords': ['은강'], 'content': '수도를 가로지른다.'}
KING = {'id': 'king', 'name': '왕', 'kind': 'person', 'keywords': [], 'content': '늙은 왕.', 'constant': True}
BOOK = {'id': '0c1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d', 'version': 1, 'name': '세계', 'entries': [KING, TOWER, RIVER]}
NEAR_TOWER = '붉은 탑 꼭대기에 별을 보는 방이 있다며? 가 보고 싶어'


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['그래요.']))
    app.state.model_router = fake
    return fake


@pytest.fixture
def embedder(app: FastAPI) -> FakeEmbedder:
    """뜻으로 찾기를 켠다(EMBEDDER=fake 와 같다)."""
    fake = FakeEmbedder()
    app.state.lore_indexer = LoreIndexer(app.state.session_factory, fake)
    app.state.lore_recall = LoreRecall(app.state.session_factory, fake, app.state.lore_indexer)
    return fake


async def indexed(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.lore_indexer.tasks))


async def start(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, headers: dict, character: CharacterCopy | None = None
) -> dict:
    await turn_on_luna(session)
    character = character or asset.add_character(make_character(world={'lorebooks': [BOOK]}))
    response = await client.post(
        CONVERSATIONS_URL, json={'character_id': str(character.id), 'model': 'luna'}, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str) -> None:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))


async def vectors(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(LoreEmbedding))


def card(router: FakeRouter) -> str:
    return router.provider.calls[-1][0][0].content


async def test_starting_a_conversation_embeds_the_entries(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, embedder: FakeEmbedder, mine: dict
):
    character = asset.add_character(make_character(world={'lorebooks': [BOOK]}))
    await start(client, session, asset, mine, character)
    await indexed(app)
    # 같은 판으로 다시 시작하면 같은 사본이다. 벡터를 다시 만들지 않는다
    await start(client, session, asset, mine, character)
    await indexed(app)

    assert await vectors(session) == 3
    models = set(await session.scalars(select(LoreEmbedding.model)))
    assert models == {embedder.model}
    assert embedder.calls[0][1] == '붉은 탑\n키워드: 마탑\n붉은 탑 꼭대기에 별을 보는 방이 있다.'


async def test_the_same_copy_is_indexed_once_at_a_time(app: FastAPI, embedder: FakeEmbedder):
    character_id = uuid.uuid4()

    app.state.lore_indexer.request(character_id)
    app.state.lore_indexer.request(character_id)

    assert len(app.state.lore_indexer.tasks) == 1
    await indexed(app)


async def test_a_near_entry_is_recalled_without_a_keyword(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    asset: FakeAsset,
    router: FakeRouter,
    embedder: FakeEmbedder,
    mine: dict,
):
    conversation = await start(client, session, asset, mine)
    await indexed(app)

    await say(client, app, mine, conversation, NEAR_TOWER)

    assert '[로어북]\n- 왕: 늙은 왕.\n- 붉은 탑: 붉은 탑 꼭대기에 별을 보는 방이 있다.' in card(router)
    assert '은빛 강' not in card(router)


async def test_without_the_embedder_only_keywords_count(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine)

    await say(client, app, mine, conversation, NEAR_TOWER)

    assert '붉은 탑' not in card(router)
    assert '- 왕: 늙은 왕.' in card(router)


async def test_a_failing_embedder_falls_back_to_keywords(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    asset: FakeAsset,
    router: FakeRouter,
    embedder: FakeEmbedder,
    mine: dict,
):
    conversation = await start(client, session, asset, mine)
    await indexed(app)
    embedder.error = 'timeout'

    await say(client, app, mine, conversation, f'{NEAR_TOWER} 은강도')

    assert '- 은빛 강: 수도를 가로지른다.' in card(router)
    assert '붉은 탑' not in card(router)


async def test_missing_vectors_are_made_when_recalling(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    asset: FakeAsset,
    router: FakeRouter,
    embedder: FakeEmbedder,
    mine: dict,
):
    conversation = await start(client, session, asset, mine)
    await indexed(app)
    await session.execute(delete(LoreEmbedding))
    await session.commit()

    await say(client, app, mine, conversation, NEAR_TOWER)
    await indexed(app)

    assert '붉은 탑' not in card(router)
    assert await vectors(session) == 3


async def test_vectors_go_with_the_copy(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, embedder: FakeEmbedder, mine: dict
):
    conversation = await start(client, session, asset, mine)
    await indexed(app)
    await client.delete(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)

    # 탈퇴는 대화와 사본을 지운다(app/withdrawal). 여기서는 사본을 바로 지운다
    await session.execute(delete(Conversation))
    await session.execute(delete(ImportedCharacter))
    await session.commit()

    assert await vectors(session) == 0
