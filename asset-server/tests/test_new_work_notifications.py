# asset-server/tests/test_new_work_notifications.py

"""
캐릭터와 세계관을 목록에 올리면 만든 사람의 팔로워에게 알리는 것(#989)을 검증한다. 실제 DB(asset_test)에서 돈다.

  - 목록에 나오게 되면(공개로 두고 게시, 게시한 뒤 공개로 바꿈) 발송함에 *.published 가 하나 적힌다.
    user_id 는 만든 사람이고 열쇠는 작품마다 하나다
  - 비공개와 링크 공개(#993)는 목록에 나오지 않아 적지 않는다
  - 이미 목록에 있는 것을 다시 게시하거나 고쳐도 적지 않는다. 내렸다가 다시 올려도 발송함에 남아 있으면 더 적지 않는다
"""

import uuid

import pytest
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import OutgoingNotification
from tests import test_characters_api as character_tests
from tests.test_characters_api import CHARACTERS_URL, OPERATOR, create, make_public, publish
from tests.test_world_listings import published
from tests.worlds import OWNER, WORLDS_URL, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

operator = character_tests.operator


async def queued(session: AsyncSession, kind: str) -> list[tuple[uuid.UUID, str, dict]]:
    session.expire_all()
    query = select(OutgoingNotification).where(OutgoingNotification.kind == kind).order_by(OutgoingNotification.id)
    return [(row.user_id, row.source_key, row.payload) for row in await session.scalars(query)]


async def set_visibility(client: AsyncClient, headers: dict, url: str, visibility: str) -> None:
    response = await client.patch(url, json={'visibility': visibility}, headers=headers)
    assert response.status_code == 200, response.text


async def test_a_listed_character_is_announced_once(client: AsyncClient, session: AsyncSession, operator: dict):
    character = await make_public(client, operator, name='아리')
    url = f'{CHARACTERS_URL}/{character["id"]}'
    await publish(client, operator, character)
    await set_visibility(client, operator, url, 'private')
    await set_visibility(client, operator, url, 'public')

    assert await queued(session, 'character.published') == [
        (
            OPERATOR,
            f'character.published:{character["id"]}',
            {'character_id': character['id'], 'name': '아리', 'creator_id': str(OPERATOR)},
        )
    ]


@pytest.mark.parametrize('visibility', ['private', 'unlisted'])
async def test_a_character_off_the_list_is_announced_when_it_is_listed(
    client: AsyncClient, session: AsyncSession, operator: dict, visibility: str
):
    character = await create(client, operator, name='버')
    url = f'{CHARACTERS_URL}/{character["id"]}'
    await set_visibility(client, operator, url, visibility)
    await publish(client, operator, character)
    assert await queued(session, 'character.published') == []

    await set_visibility(client, operator, url, 'public')

    assert [row[1] for row in await queued(session, 'character.published')] == [
        f'character.published:{character["id"]}'
    ]


async def test_a_listed_world_is_announced(client: AsyncClient, session: AsyncSession, signing_key: SigningKey):
    owner = bearer(signing_key, OWNER)
    world = await published(client, owner, name='여름')
    hidden = await published(client, owner, public=False, name='비공개')

    assert await queued(session, 'world.published') == [
        (OWNER, f'world.published:{world["id"]}', {'world_id': world['id'], 'name': '여름', 'creator_id': str(OWNER)})
    ]
    await set_visibility(client, owner, f'{WORLDS_URL}/{hidden["id"]}', 'public')
    assert len(await queued(session, 'world.published')) == 2
