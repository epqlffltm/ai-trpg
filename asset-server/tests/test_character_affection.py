# asset-server/tests/test_character_affection.py

"""
캐릭터의 호감도(보이는 방식, 시작 값, 단계, 오르내리는 규칙)를 검증한다. 판의 형식 3. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 만들고 고치고 게시하면 판에 굳는다. null 로 비우면 호감도가 없는 캐릭터다. 보내지 않으면 그대로다
  - 칸의 검사: 단계는 0 에서 시작해 경계가 오르고 이름이 겹치지 않는다. 값과 바꾸는 크기의 범위,
    0 을 바꾸는 규칙, 같은 규칙 id, 모르는 행동, 개수
  - 게시를 막는 것: 규칙이 없는 물건이나 장소를 가리킨다(건넸다, 썼다는 물건, 갔다는 장소)
  - 형식 1, 2 의 판은 호감도가 없는 것으로 읽힌다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.documents import DOCUMENT_FORMAT
from app.characters.models import AFFECTION_MAX_STAGES, CharacterVersion
from app.main import API_PREFIX

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}
WORLD = {
    'places': [{'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None}],
    'start_place': 'cafe',
    'items': [{'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'image_id': None}],
}
AFFECTION = {
    'display': 'stage',
    'start': 10,
    'stages': [{'name': '낯섦', 'at': 0}, {'name': '친구', 'at': 30}, {'name': '연인', 'at': 70}],
    'rules': [
        {'id': 'gift', 'on': {'kind': 'give_item', 'target': 'scarf'}, 'change': 5, 'once': False},
        {'id': 'date', 'on': {'kind': 'reach_place', 'target': 'cafe'}, 'change': 10, 'once': True},
        {'id': 'rude', 'on': {'kind': 'use_item', 'target': 'scarf'}, 'change': -3, 'once': False},
    ],
}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    body = {'name': '세라', 'starts': [START], **WORLD, 'affection': AFFECTION, **fields}
    response = await client.post(CHARACTERS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def patch(client: AsyncClient, headers: dict, character: dict, body: dict):
    return await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json=body, headers=headers)


async def publish(client: AsyncClient, headers: dict, character: dict):
    return await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=headers)


async def test_affection_is_kept_and_frozen_in_the_version(client: AsyncClient, operator: dict):
    character = await create(client, operator)

    document = (await publish(client, operator, character)).json()['document']

    assert character['affection'] == AFFECTION
    assert (document['format'], document['affection']) == (DOCUMENT_FORMAT, AFFECTION)


async def test_defaults_fill_the_display_the_start_and_the_rules(client: AsyncClient, operator: dict):
    character = await create(client, operator, affection={'stages': [{'name': '보통', 'at': 0}]})

    assert character['affection'] == {
        'display': 'number',
        'start': 0,
        'stages': [{'name': '보통', 'at': 0}],
        'rules': [],
    }


async def test_null_clears_and_leaving_it_out_keeps(client: AsyncClient, operator: dict):
    character = await create(client, operator)

    kept = (await patch(client, operator, character, {'name': '세라 2'})).json()
    cleared = (await patch(client, operator, character, {'affection': None})).json()
    document = (await publish(client, operator, character)).json()['document']

    assert kept['affection'] == AFFECTION
    assert (cleared['affection'], document['affection']) == (None, None)


async def test_affection_can_be_replaced(client: AsyncClient, operator: dict):
    character = await create(client, operator, affection=None)
    changed = {**AFFECTION, 'display': 'number', 'start': 50}

    response = await patch(client, operator, character, {'affection': changed})
    draft = (await client.get(f'{CHARACTERS_URL}/{character["id"]}', headers=operator)).json()

    assert (response.json()['affection'], draft['affection']) == (changed, changed)


def with_affection(**changes) -> dict:
    return {'affection': {**AFFECTION, **changes}}


def with_rule(**changes) -> dict:
    return with_affection(rules=[{**AFFECTION['rules'][0], **changes}])


@pytest.mark.parametrize(
    'body',
    [
        with_affection(stages=[]),
        with_affection(stages=[{'name': '친구', 'at': 30}]),
        with_affection(stages=[{'name': '낯섦', 'at': 0}, {'name': '친구', 'at': 0}]),
        with_affection(stages=[{'name': '낯섦', 'at': 0}, {'name': '친구', 'at': 50}, {'name': '연인', 'at': 40}]),
        with_affection(stages=[{'name': '낯섦', 'at': 0}, {'name': '낯섦', 'at': 50}]),
        with_affection(stages=[{'name': f'단계{index}', 'at': index} for index in range(AFFECTION_MAX_STAGES + 1)]),
        with_affection(stages=[{'name': '낯섦', 'at': 0}, {'name': '끝', 'at': 101}]),
        with_affection(start=101),
        with_affection(display='hidden'),
        with_rule(change=0),
        with_rule(change=21),
        with_rule(on={'kind': 'kiss', 'target': 'scarf'}),
        with_affection(rules=[AFFECTION['rules'][0], {**AFFECTION['rules'][1], 'id': 'gift'}]),
        with_affection(secret=1),
    ],
)
async def test_a_bad_affection_is_refused(client: AsyncClient, operator: dict, body: dict):
    character = await create(client, operator)

    response = await patch(client, operator, character, body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    'rule',
    [
        {'id': 'x', 'on': {'kind': 'give_item', 'target': 'ring'}, 'change': 1},
        {'id': 'x', 'on': {'kind': 'use_item', 'target': 'cafe'}, 'change': 1},
        {'id': 'x', 'on': {'kind': 'reach_place', 'target': 'scarf'}, 'change': 1},
    ],
)
async def test_a_rule_about_something_missing_blocks_publishing(client: AsyncClient, operator: dict, rule: dict):
    character = await create(client, operator, affection={**AFFECTION, 'rules': [rule]})

    refused = await publish(client, operator, character)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['problems'] == ['affection_target_missing']


async def test_versions_before_format_three_have_no_affection(
    client: AsyncClient, operator: dict, session: AsyncSession
):
    character = await create(client, operator)
    published = (await publish(client, operator, character)).json()
    version = await session.get(CharacterVersion, uuid.UUID(published['id']))
    version.document = {**{key: value for key, value in version.document.items() if key != 'affection'}, 'format': 2}
    await session.commit()

    response = await client.get(f'{CHARACTERS_URL}/{character["id"]}/versions/1', headers=operator)

    assert response.json()['document']['affection'] is None
