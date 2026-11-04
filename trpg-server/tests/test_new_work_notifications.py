# trpg-server/tests/test_new_work_notifications.py

"""
시나리오를 목록에 올리면 만든 사람의 팔로워에게 알리는 것(#989)을 검증한다. 실제 DB(game_test)에서 돈다.

  - 공개하면 발송함에 scenario.published 가 하나 적힌다. user_id 는 만든 사람이고 열쇠는 시나리오마다 하나다
  - 링크 공개(#993)로 공개하면 적지 않는다. 링크 공개를 풀어 목록에 나오게 되면 적는다
  - 내렸다가 다시 올려도 발송함에 같은 열쇠가 남아 있으면 더 적지 않고, 조치는 그대로 된다
    (보낸 뒤에 다시 올린 것은 알림 서버가 처음 한 번만 나눠 넣는다)
  - 이미 목록에 있는 것의 소개를 고치거나 다른 판으로 바꿔도 적지 않는다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import OutgoingNotification
from tests import test_listings_api as listing_tests
from tests.test_listings_api import (
    ME,
    create_scenario,
    listing_url,
    make_public,
    publish_version,
    write_page,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

my_headers = listing_tests.my_headers


async def queued(session: AsyncSession) -> list[tuple[uuid.UUID, str, str, dict]]:
    rows = await session.scalars(select(OutgoingNotification).order_by(OutgoingNotification.id))
    return [(row.user_id, row.kind, row.source_key, row.payload) for row in rows]


async def publish(client: AsyncClient, headers: dict, scenario: dict, version: int | None) -> None:
    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': version}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text


async def test_publishing_queues_one_announcement(client: AsyncClient, session: AsyncSession, my_headers: dict):
    scenario = await make_public(client, my_headers, title='잊힌 탑')

    assert await queued(session) == [
        (
            ME,
            'scenario.published',
            f'scenario.published:{scenario["id"]}',
            {'scenario_id': scenario['id'], 'title': '잊힌 탑', 'creator_id': str(ME)},
        )
    ]


async def test_republishing_while_queued_adds_nothing(client: AsyncClient, session: AsyncSession, my_headers: dict):
    scenario = await make_public(client, my_headers, title='잊힌 탑')
    await publish(client, my_headers, scenario, None)
    await publish(client, my_headers, scenario, 1)
    await write_page(client, my_headers, scenario, tagline='고쳤다')
    number = await publish_version(client, my_headers, scenario)
    await publish(client, my_headers, scenario, number)

    assert len(await queued(session)) == 1


async def test_republishing_after_it_was_sent_queues_it_again(
    client: AsyncClient, session: AsyncSession, my_headers: dict
):
    scenario = await make_public(client, my_headers, title='잊힌 탑')
    await session.execute(delete(OutgoingNotification))
    await session.commit()
    await publish(client, my_headers, scenario, None)
    await publish(client, my_headers, scenario, 1)

    # 처음인지는 알림 서버가 본다(같은 열쇠는 다시 나눠 넣지 않는다)
    assert [row[2] for row in await queued(session)] == [f'scenario.published:{scenario["id"]}']


async def test_a_link_only_scenario_is_announced_when_it_is_listed(
    client: AsyncClient, session: AsyncSession, my_headers: dict
):
    scenario = await create_scenario(client, my_headers, title='비밀 탑')
    number = await publish_version(client, my_headers, scenario)
    await write_page(client, my_headers, scenario, unlisted=True)
    await publish(client, my_headers, scenario, number)
    assert await queued(session) == []

    await write_page(client, my_headers, scenario, unlisted=False)

    assert [row[1] for row in await queued(session)] == ['scenario.published']
