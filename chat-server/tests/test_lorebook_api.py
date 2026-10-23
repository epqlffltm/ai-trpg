# chat-server/tests/test_lorebook_api.py

"""
로어북을 API 로 검증한다(#672). 실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 대화의 판 사본에 로어북이 남는다
  - 카드의 "[로어북]" 에 상시 항목이 늘 가고, 이번에 보낸 말에 키워드가 나오면 그 항목이 간다(기억 메모 뒤, 지금 앞)
  - 건넬 때 덧붙인 한마디의 키워드도 본다
  - 로어북이 없는 캐릭터면 블록이 없다
"""

import asyncio

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import ImportedCharacter
from tests.assets import FakeAsset, make_character
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

BOOK = {
    'id': '0c1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d',
    'version': 2,
    'name': '제국',
    'entries': [
        {'id': 'emperor', 'name': '황제', 'kind': 'person', 'keywords': [], 'content': '늙은 황제.', 'constant': True},
        {
            'id': 'city',
            'name': '가나폴리아',
            'kind': 'place',
            'keywords': ['수도'],
            'content': '일곱 언덕.',
            'constant': False,
        },
        {
            'id': 'rose',
            'name': '붉은 장미',
            'kind': 'item',
            'keywords': ['장미'],
            'content': '황실의 꽃.',
            'constant': False,
        },
    ],
}
WORLD = {
    'lorebooks': [BOOK],
    'items': [{'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'image_id': None}],
    'start_items': [{'item': 'scarf', 'count': 1}],
}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['그렇군요.']))
    app.state.model_router = fake
    return fake


async def start(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, headers: dict, world: dict | None
) -> dict:
    await turn_on_luna(session)
    character = asset.add_character(make_character(world=world))
    response = await client.post(
        CONVERSATIONS_URL, json={'character_id': str(character.id), 'model': 'luna'}, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def send(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, path: str, body: dict) -> None:
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/{path}', json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))


def card(router: FakeRouter) -> str:
    return router.provider.calls[-1][0][0].content


async def test_the_copy_keeps_the_lorebooks(client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict):
    await start(client, session, asset, mine, WORLD)

    document = await session.scalar(select(ImportedCharacter.document))

    assert document['lorebooks'][0]['name'] == '제국'
    assert [item['id'] for item in document['lorebooks'][0]['entries']] == ['emperor', 'city', 'rose']


async def test_constant_and_mentioned_entries_reach_the_card(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)

    await send(client, app, mine, conversation, 'messages', {'content': '안녕'})
    first = card(router)
    await send(client, app, mine, conversation, 'messages', {'content': '수도에 가 보고 싶어'})
    second = card(router)

    assert '[로어북]\n- 황제: 늙은 황제.' in first
    assert '가나폴리아' not in first
    assert '[로어북]\n- 황제: 늙은 황제.\n- 가나폴리아: 일곱 언덕.' in second
    assert second.index('[로어북]') < second.index('[지금]')


async def test_the_words_with_a_gift_are_scanned(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)

    await send(client, app, mine, conversation, 'actions', {'kind': 'give', 'item': 'scarf', 'words': '장미 대신이야'})

    assert '- 붉은 장미: 황실의 꽃.' in card(router)


async def test_without_lorebooks_there_is_no_block(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, None)

    await send(client, app, mine, conversation, 'messages', {'content': '수도'})

    assert '[로어북]' not in card(router)
