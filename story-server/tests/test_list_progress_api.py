# story-server/tests/test_list_progress_api.py

"""
세션 목록의 진행(GET /conversations 의 progress)을 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 새 세션은 1일째 처음의 시간대이고 엔딩이 없다. 판의 기한이 실린다
  - 행동으로 날이 가면 목록의 날짜가 따라간다
  - 엔딩을 보면 그 id 와 이름이 실린다. 끝을 고른 세계관이면 후일담이 아니고, 후일담을 고른 세계관이면 후일담이다
  - 가지를 바꾸면 그 가지의 진행이 된다(따로 저장하지 않고 읽을 때 센다)
"""

import asyncio

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from tests.assets import FakeAsset
from tests.engine_worlds import confession, ending, member
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = CONVERSATIONS_URL.replace('/conversations', '/messages')
MINA = {**member('mina', home='home', start=80, confession=confession('연인')), 'character': {'name': '미나'}}
WITH_MINA = {**ending('with_mina', 'confess_success', 'mina'), 'name': '미나와 함께'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
async def model_on(clean_tables: None, session: AsyncSession, app: FastAPI) -> None:
    await turn_on_luna(session)
    app.state.model_router = FakeRouter()


async def act(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict, body: dict) -> list:
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/actions', json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)


async def progress(client: AsyncClient, headers: dict) -> dict:
    """목록의 맨 위 세션의 진행."""
    response = await client.get(CONVERSATIONS_URL, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['items'][0]['progress']


async def test_a_new_session_starts_on_day_one_without_an_ending(
    client: AsyncClient, model_on: None, asset: FakeAsset, mine: dict
):
    await start_with_luna(client, asset, mine, {'deadline_days': 30})

    assert await progress(client, mine) == {
        'day': 1,
        'slot': 'morning',
        'deadline_days': 30,
        'ending': None,
        'ending_name': None,
        'epilogue': False,
    }


async def test_the_day_follows_the_actions(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, mine: dict
):
    conversation = await start_with_luna(client, asset, mine)

    await act(app, client, mine, conversation, {'kind': 'end_day'})

    assert (await progress(client, mine))['day'] == 2


@pytest.mark.parametrize(('after_ending', 'epilogue'), [('end', False), ('epilogue', True)])
async def test_an_ending_is_named_and_the_epilogue_is_told_apart(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, mine: dict, after_ending: str, epilogue: bool
):
    fields = {'cast': [MINA], 'endings': [WITH_MINA], 'after_ending': after_ending}
    conversation = await start_with_luna(client, asset, mine, fields)

    await act(app, client, mine, conversation, {'kind': 'confess', 'cast': 'mina'})

    read = await progress(client, mine)
    assert (read['ending'], read['ending_name'], read['epilogue']) == ('with_mina', '미나와 함께', epilogue)


async def test_choosing_another_branch_shows_its_progress(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, mine: dict
):
    conversation = await start_with_luna(client, asset, mine)
    first = (await act(app, client, mine, conversation, {'kind': 'pass_time'}))[-1][1]['message']
    await act(app, client, mine, conversation, {'kind': 'end_day'})
    assert (await progress(client, mine))['day'] == 2
    # 첫 답을 다시 써서 하루를 마치기 전의 가지로 돌아간다
    response = await client.post(f'{MESSAGES_URL}/{first["id"]}/regenerate', headers=mine)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))

    assert ((await progress(client, mine))['day'], (await progress(client, mine))['slot']) == (1, 'night')
