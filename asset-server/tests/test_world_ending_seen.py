# asset-server/tests/test_world_ending_seen.py

"""
조건의 ending_seen(회차 혜택, 판의 형식 5)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 이벤트의 조건에 ending_seen(target: 엔딩)을 적고 게시하면 판(형식 5)에 그대로 굳는다. target 이 없으면 422 다
  - 이 세계관에 없는 엔딩을 가리키면 게시하지 못한다(ending_target_missing)
  - 계정에 남지 않는 엔딩(unlock 이 거짓)을 봐야 열리는 이벤트는 열릴 수 없어 알린다(event_unreachable)
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.worlds.documents import DOCUMENT_FORMAT
from tests.worlds import (
    MEET,
    OWNER,
    SOLO_ENDING,
    WORLDS_URL,
    bearer,
    character,
    check,
    create_world,
    full_world,
    publish,
)

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


async def world_with(client: AsyncClient, headers: dict, **fields) -> dict:
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    return await create_world(client, headers, {**full_world(ari['id'], beo['id']), **fields})


def secret(ending_id: str | None) -> dict:
    """그 엔딩을 본 적이 있으면 열리는 이벤트."""
    item = {'kind': 'ending_seen'} if ending_id is None else {'kind': 'ending_seen', 'target': ending_id}
    return {'id': 'secret', 'name': '숨은 이야기', 'when': {'match': 'all', 'items': [item]}, 'scene': {'text': '장면'}}


async def test_the_condition_is_frozen_in_a_format_five_version(client: AsyncClient, owner: dict):
    world = await world_with(client, owner, events=[MEET, secret('solo')])

    response = await publish(client, owner, world)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    document = response.json()['document']
    assert DOCUMENT_FORMAT == document['format'] == 5
    assert document['events'][1]['when']['items'] == [
        {'kind': 'ending_seen', 'target': 'solo', 'value': None, 'count': 1}
    ]


async def test_a_condition_without_a_target_is_refused(client: AsyncClient, owner: dict):
    ari, beo = await character(client, owner, '아리'), await character(client, owner, '버')
    body = {**full_world(ari['id'], beo['id']), 'events': [MEET, secret(None)]}

    response = await client.post(WORLDS_URL, json=body, headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_missing_ending_blocks(client: AsyncClient, owner: dict):
    world = await world_with(client, owner, events=[MEET, secret('ghost')])

    checked = await check(client, owner, world)
    response = await publish(client, owner, world)

    assert checked['problems'] == ['ending_target_missing']
    assert response.status_code == status.HTTP_409_CONFLICT


async def test_an_ending_left_off_the_account_can_never_open_the_event(client: AsyncClient, owner: dict):
    hidden_solo = {**SOLO_ENDING, 'unlock': False}
    world = await world_with(client, owner, events=[MEET, secret('solo')], endings=[hidden_solo])
    recorded = await world_with(client, owner, events=[MEET, secret('solo')])

    assert 'event_unreachable' in (await check(client, owner, world))['warnings']
    assert 'event_unreachable' not in (await check(client, owner, recorded))['warnings']
