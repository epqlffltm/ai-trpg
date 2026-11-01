# story-server/tests/test_chapters_api.py

"""
장(판의 형식 6, docs/architecture/chapters.md)을 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 모델은 가짜다(tests/assets.py, tests/models.py).

보는 것.
  - 형식 6 의 판으로 세션을 시작하면 첫 장이다. view 에는 닿은 장만, 열린 장소와 그 사이의 길만 실린다
  - 닫힌 장소로 가면 422 cannot_move 이고 아무것도 저장하지 않는다
  - 장이 넘어간 행동 말에 그 장(chapter_id)과 장의 시작 글이 남고, 모델에도 그 글이 간다. 그 뒤로 새 장소가 보인다
  - 기록 내려받기에 장이 넘어간 표시가 남는다
"""

import asyncio

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Message
from tests.assets import FakeAsset
from tests.engine_worlds import condition
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, WORLD_FIELDS, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

PLACES = [{'id': 'home', 'name': '집'}, {'id': 'beach', 'name': '해변'}, {'id': 'square', 'name': '광장'}]
PATHS = [
    {'a': 'home', 'b': 'beach', 'minutes': 30},
    {'a': 'home', 'b': 'square', 'minutes': 30},
    {'a': 'beach', 'b': 'square', 'minutes': 10},
]
# 1장(여름의 시작)에서 해변에 가면 2장(축제)이 열리고 광장이 열린다
CHAPTERS = [
    {'id': 'summer', 'name': '여름의 시작', 'when': {'match': 'all', 'items': []}, 'opens': {}},
    {
        'id': 'festival',
        'name': '축제',
        'when': {'match': 'all', 'items': [condition('reach_place', 'beach')]},
        'opens': {'places': ['square'], 'events': []},
    },
]
FIELDS = {'format': 6, 'places': PLACES, 'paths': PATHS, 'chapters': CHAPTERS}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


@pytest.fixture
async def started(
    clean_tables: None, client: AsyncClient, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
) -> dict:
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine, {**WORLD_FIELDS, **FIELDS})


async def act(client: AsyncClient, app: FastAPI, headers: dict, conversation_id: str, body: dict):
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation_id}/actions', json=body, headers=headers)
    await asyncio.gather(*list(app.state.turns))
    return response


async def detail(client: AsyncClient, headers: dict, conversation_id: str) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation_id}', headers=headers)).json()


def place_ids(view: dict) -> list[str]:
    return [place['id'] for place in view['places']]


async def test_a_session_starts_in_the_first_chapter_and_sees_only_open_places(
    client: AsyncClient, started: dict, mine: dict
):
    read = await detail(client, mine, started['id'])

    assert read['state']['chapter'] == 'summer'
    assert read['view']['chapters'] == [{'id': 'summer', 'name': '여름의 시작'}]
    assert place_ids(read['view']) == ['home', 'beach']
    assert [place['id'] for place in read['view']['map']] == ['home', 'beach']
    assert read['view']['paths'] == [{'a': 'home', 'b': 'beach', 'minutes': 30}]


async def test_a_closed_place_is_refused(
    client: AsyncClient, app: FastAPI, session: AsyncSession, started: dict, mine: dict
):
    response = await act(client, app, mine, started['id'], {'kind': 'move', 'place': 'square'})

    assert (response.status_code, response.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'cannot_move')
    assert await session.scalar(select(func.count()).select_from(Message)) == 0


async def test_the_action_that_advances_records_the_chapter_and_tells_the_model(
    client: AsyncClient, app: FastAPI, router: FakeRouter, started: dict, mine: dict
):
    response = await act(client, app, mine, started['id'], {'kind': 'move', 'place': 'beach'})

    assert response.status_code == status.HTTP_200_OK, response.text
    read = await detail(client, mine, started['id'])
    action = next(message for message in read['messages'] if message['role'] == 'action')
    assert action['chapter_id'] == 'festival'
    assert action['content'].endswith('2장 「축제」이(가) 시작됐다.')
    messages, _ = router.provider.calls[0]
    assert '2장 「축제」이(가) 시작됐다.' in messages[-1].content
    assert read['state']['chapter'] == 'festival'
    assert [chapter['id'] for chapter in read['view']['chapters']] == ['summer', 'festival']
    assert place_ids(read['view']) == ['home', 'beach', 'square']
    assert len(read['view']['paths']) == 3
    # 그 뒤로 광장에 갈 수 있다
    moved = await act(client, app, mine, started['id'], {'kind': 'move', 'place': 'square'})
    assert moved.status_code == status.HTTP_200_OK, moved.text


async def test_the_transcript_marks_the_chapter(client: AsyncClient, app: FastAPI, started: dict, mine: dict):
    await act(client, app, mine, started['id'], {'kind': 'move', 'place': 'beach'})

    response = await client.get(f'{CONVERSATIONS_URL}/{started["id"]}/transcript?format=txt', headers=mine)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert '장: 축제' in response.text
