# story-server/tests/test_lorebooks_api.py

"""
세계관의 로어북이 카드에 들어가는 것을 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 모델은 가짜다(tests/assets.py, tests/models.py).

보는 것.
  - 상시 항목은 늘, 키워드 항목은 이번 말이나 최근 말에 키워드가 나올 때 카드의 [로어북]에 들어간다
  - 로어북이 없는 세계관의 카드에는 [로어북]이 없다
"""

import asyncio

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from tests.assets import FakeAsset
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

LOREBOOK = {
    'id': '11111111-2222-4333-8444-555555555555',
    'version': 2,
    'name': '여름 마을의 설정',
    'entries': [
        {'id': 'sea', 'name': '바다', 'kind': 'place', 'keywords': [], 'content': '마을 앞의 바다.', 'constant': True},
        {
            'id': 'well',
            'name': '우물',
            'kind': 'place',
            'keywords': ['우물'],
            'content': '소원을 빈다.',
            'constant': False,
        },
    ],
}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


@pytest.fixture
async def model_on(clean_tables: None, session: AsyncSession) -> None:
    await turn_on_luna(session)


async def card_after(
    app: FastAPI, client: AsyncClient, router: FakeRouter, headers: dict, conversation: dict, text: str
):
    """말을 하나 보내고 모델에 간 카드를 돌려준다."""
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': text}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return router.provider.calls[-1][0][0].content


async def test_constant_and_mentioned_entries_go_to_the_card(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine, {'lorebooks': [LOREBOOK]})

    plain = await card_after(app, client, router, mine, conversation, '안녕')
    mentioned = await card_after(app, client, router, mine, conversation, '우물에 가 볼까?')

    assert '[로어북]\n- 바다: 마을 앞의 바다.' in plain
    assert '우물' not in plain
    assert '[로어북]\n- 바다: 마을 앞의 바다.\n- 우물: 소원을 빈다.' in mentioned


async def test_a_world_without_lorebooks_has_no_block(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine)

    assert '[로어북]' not in await card_after(app, client, router, mine, conversation, '안녕')
