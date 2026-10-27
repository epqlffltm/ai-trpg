# story-server/tests/test_world_view_api.py

"""
세션 읽기의 view(GET /conversations/{id})를 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 실루엣 인물은 장면에 들어오기 전에는 가려지고, 답의 장면에 들어오면 보인다(만남)
  - 열린 이벤트와 기다리는 선택지가 실린다
  - 계정에 남은 엔딩은 다른 세션에서도 이름이 보인다. 못 본 엔딩은 힌트만이다
  - 지도: 가 본 곳은 떠난 뒤에도 가 본 곳이고, 거기 있는 만난 인물이 보인다
  - 판의 문서(document)는 아직 그대로 실린다(화면이 view 로 옮긴 뒤 뺀다)
"""

import asyncio

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from tests.assets import FakeAsset
from tests.engine_worlds import condition, confession, ending, event, member
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}]
# 미나는 집에(보임), 준은 해변에(실루엣) 산다
CAST = [
    {**member('mina', home='home', start=80, confession=confession('연인')), 'character': {'name': '미나'}},
    {**member('jun', home='beach'), 'character': {'name': '준'}, 'reveal': 'silhouette'},
]
SHELL = event(
    'shell',
    condition('reach_place', 'beach'),
    choices=[{'id': 'keep', 'text': '조개를 줍는다', 'effects': []}],
)
ENDINGS = [
    {**ending('with_mina', 'confess_success', 'mina'), 'hint': '오래 알던 사람에게.'},
    {**ending('with_jun', 'confess_success', 'jun'), 'hint': '바다에서 만난 사람에게.'},
]


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
async def model_on(clean_tables: None, session: AsyncSession, app: FastAPI) -> None:
    await turn_on_luna(session)
    app.state.model_router = FakeRouter()


async def start(client: AsyncClient, asset: FakeAsset, headers: dict) -> dict:
    fields = {'paths': PATHS, 'cast': CAST, 'events': [SHELL], 'endings': ENDINGS}
    return await start_with_luna(client, asset, headers, fields)


async def act(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict, body: dict) -> list:
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/actions', json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)


async def view_of(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['view']


async def test_a_silhouette_is_revealed_once_met_in_a_scene(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, mine: dict
):
    conversation = await start(client, asset, mine)

    before = (await view_of(client, mine, conversation))['cast']
    await act(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})
    after = await view_of(client, mine, conversation)

    assert [(item['id'], item['reveal'], item['name']) for item in before] == [
        ('mina', 'shown', '미나'),
        ('jun', 'silhouette', None),
    ]
    # 해변의 장면에 준이 들어왔다. 미나는 아직 장면에 들어온 적이 없다
    assert [(item['id'], item['reveal'], item['name'], item['met']) for item in after['cast']] == [
        ('mina', 'shown', '미나', False),
        ('jun', 'shown', '준', True),
    ]
    # 해변에서 열린 이벤트와 그 선택지가 실린다. 조건은 없다
    assert after['events'] == [
        {
            'id': 'shell',
            'name': 'shell',
            'cast': [],
            'image_id': None,
            'choices': [{'id': 'keep', 'text': '조개를 줍는다'}],
        }
    ]


async def test_an_ending_kept_on_the_account_is_named_in_another_session(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, mine: dict
):
    first = await start(client, asset, mine)
    await act(app, client, mine, first, {'kind': 'confess', 'cast': 'mina'})

    # 같은 세계관으로 새 세션을 시작한다
    body = {'world_id': first['world']['id'], 'model': 'luna'}
    second = (await client.post(CONVERSATIONS_URL, json=body, headers=mine)).json()
    endings = (await view_of(client, mine, second))['endings']

    assert [(item['id'], item['seen'], item['name'], item['hint']) for item in endings] == [
        ('with_mina', True, 'with_mina', '오래 알던 사람에게.'),
        ('with_jun', False, None, '바다에서 만난 사람에게.'),
    ]


async def test_the_map_keeps_visited_places_and_shows_met_members_there(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, mine: dict
):
    conversation = await start(client, asset, mine)

    before = (await view_of(client, mine, conversation))['map']
    await act(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})
    await act(app, client, mine, conversation, {'kind': 'move', 'place': 'home'})
    after = (await view_of(client, mine, conversation))['map']

    assert before == [{'id': 'home', 'visited': True, 'cast': []}, {'id': 'beach', 'visited': False, 'cast': []}]
    # 해변은 떠난 뒤에도 가 본 곳이고 거기서 만난 준이 보인다. 집에 돌아와 미나도 장면에 들어왔다
    assert after == [
        {'id': 'home', 'visited': True, 'cast': ['mina']},
        {'id': 'beach', 'visited': True, 'cast': ['jun']},
    ]


async def test_the_document_is_still_carried_for_now(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, mine: dict
):
    conversation = await start(client, asset, mine)

    read = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()

    assert read['world']['document']['endings'][0]['id'] == 'with_mina'
    assert read['view']['name'] == read['world']['name']
