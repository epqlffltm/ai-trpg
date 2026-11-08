# asset-server/tests/test_my_works_counts.py

"""
내 작품 목록의 쓰인 수와 관심 수, 정렬(#1165)을 검증한다.
내 캐릭터 목록(GET /characters)과 내 세계관 목록(GET /worlds)이다.

보는 것.
  - 줄마다 쓰인 수(start_count, 모든 기간)와 관심 수(heart_count)가 실린다. 작품의 행에 적힌 값이다
  - 기본은 최근에 고친 것부터, sort=started 면 쓰인 수가 많은 것부터, 같으면 최근에 고친 것부터다
  - 모르는 차례는 422 다
수는 작품의 행에 바로 적는다. 받아 오는 일(app/stats/)과 관심 두기(app/hearts/)는 각자의 테스트가 본다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character
from app.worlds.models import World
from tests import test_characters_api as characters
from tests.worlds import WORLDS_URL, create_world

pytestmark = pytest.mark.usefixtures('clean_tables')

operator = characters.operator


async def counted(session: AsyncSession, model, work_id: str, starts: int, hearts: int) -> None:
    """작품의 행에 쓰인 수와 관심 수를 적는다. 고친 시각은 그대로 둔다."""
    await session.execute(
        update(model)
        .where(model.id == work_id)
        .values(start_count=starts, heart_count=hearts, updated_at=model.updated_at)
    )
    await session.commit()


async def names(client: AsyncClient, url: str, headers: dict, **params) -> list[tuple[str, int, int]]:
    response = await client.get(url, params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return [(item['name'], item['start_count'], item['heart_count']) for item in response.json()['items']]


async def test_my_characters_carry_their_counts_and_sort_by_starts(
    client: AsyncClient, operator: dict, session: AsyncSession
):
    quiet = await characters.create(client, operator, name='조용한')
    busy = await characters.create(client, operator, name='바쁜')
    fresh = await characters.create(client, operator, name='새것')
    await counted(session, Character, quiet['id'], 3, 1)
    await counted(session, Character, busy['id'], 40, 7)
    await counted(session, Character, fresh['id'], 3, 0)

    recent = await names(client, characters.CHARACTERS_URL, operator)
    started = await names(client, characters.CHARACTERS_URL, operator, sort='started')

    assert recent == [('새것', 3, 0), ('바쁜', 40, 7), ('조용한', 3, 1)]
    # 같은 수(3)는 최근에 고친 것부터다
    assert started == [('바쁜', 40, 7), ('새것', 3, 0), ('조용한', 3, 1)]


async def test_my_worlds_carry_their_counts_and_sort_by_starts(
    client: AsyncClient, operator: dict, session: AsyncSession
):
    first = await create_world(client, operator, {'genre': 'romance', 'name': '여름 학원'})
    await create_world(client, operator, {'genre': 'romance', 'name': '겨울 학원'})
    await counted(session, World, first['id'], 9, 2)

    recent = await names(client, WORLDS_URL, operator)
    started = await names(client, WORLDS_URL, operator, sort='started')

    assert recent == [('겨울 학원', 0, 0), ('여름 학원', 9, 2)]
    assert started == [('여름 학원', 9, 2), ('겨울 학원', 0, 0)]


@pytest.mark.parametrize('url', [characters.CHARACTERS_URL, WORLDS_URL])
async def test_an_unknown_order_is_refused(client: AsyncClient, operator: dict, url: str):
    response = await client.get(url, params={'sort': 'popular'}, headers=operator)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
