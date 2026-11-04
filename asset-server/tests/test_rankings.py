# asset-server/tests/test_rankings.py

"""
작품마다의 시작 수(app/stats/)와 랭킹(app/rankings/, #985)을 검증한다. 실제 DB(asset_test)에서 돈다.

  - 받기: chat 과 story 서버의 내부 주소를 그 서버의 비밀로 서명해 부르고, 그 종류의 줄을 통째로 바꾼다.
    받지 못하면(닿지 못함, 5xx, 모양이 틀림) 쌓아 둔 수를 그대로 둔다. 주소가 없으면 부르지 않는다
  - 랭킹: 최근의 수가 많은 것부터다. 0 인 것, 공개 목록에 나오지 않는 것(비공개), 볼 수 없는 등급은 빠진다.
    보는 사람의 설정(hide_adult, orientation)으로 거른다. 받은 적이 없으면 비어 있고 refreshed_at 이 null 이다
  - 주소를 적었는데 비밀이 없으면 뜨지 않는다
  - 받은 모든 수를 작품의 카드(start_count)에 옮겨 적고, 공개 목록은 sort=popular 면 랭킹과 같은 차례다
"""

import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.stats.client import STARTS_PATHS
from app.stats.models import WorkKind, WorkStarts
from app.stats.refresher import StartsRefresher, build_sources
from tests import test_characters_api as character_tests
from tests.conftest import TEST_SECRETS, make_test_settings
from tests.test_characters_api import CHARACTERS_URL, make_public
from tests.test_world_listings import published
from tests.worlds import OWNER, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

operator = character_tests.operator
adult = character_tests.adult

RANKINGS_URL = f'{API_PREFIX}/rankings'
CHARACTER_LISTINGS = f'{API_PREFIX}/listings/characters'
WORLD_LISTINGS = f'{API_PREFIX}/listings/worlds'
NOW = datetime(2026, 11, 4, 3, 0, tzinfo=UTC)


def starts_body(*items: tuple[str, int, int]) -> dict:
    return {
        'recent_days': 7,
        'items': [{'work_id': work, 'total': total, 'recent': recent} for work, total, recent in items],
    }


def refresher_for(app: FastAPI, handler, **settings) -> StartsRefresher:
    """가짜 chat·story 서버(handler)로 받는 바퀴. 주소는 설정으로 정한다."""
    sources = build_sources(make_test_settings(**settings))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return StartsRefresher(app.state.session_factory, client, sources, interval=3600, clock=lambda: NOW)


async def stored(session: AsyncSession) -> list[tuple[str, uuid.UUID, int, int]]:
    rows = await session.execute(select(WorkStarts.kind, WorkStarts.work_id, WorkStarts.total, WorkStarts.recent))
    return sorted(rows.all())


async def seed(session: AsyncSession, kind: WorkKind, *items: tuple[str, int, int]) -> None:
    for work, total, recent in items:
        session.add(
            WorkStarts(kind=kind, work_id=uuid.UUID(work), total=total, recent=recent, recent_days=7, refreshed_at=NOW)
        )
    await session.commit()


async def ranked(client: AsyncClient, kind: str, headers: dict | None = None, **params) -> list[tuple[int, str, int]]:
    response = await client.get(f'{RANKINGS_URL}/{kind}', params=params, headers=headers or {})
    assert response.status_code == status.HTTP_200_OK, response.text
    key = 'character' if kind == 'characters' else 'world'
    return [(item['rank'], item[key]['name'], item['starts']) for item in response.json()['items']]


# --- 받기 ---


async def test_fetches_signed_and_replaces_the_rows(app: FastAPI, session: AsyncSession):
    old, kept, fresh, world = (str(uuid.uuid4()) for _ in range(4))
    await seed(session, WorkKind.CHARACTER, (old, 9, 9))
    await seed(session, WorkKind.WORLD, (world, 1, 1))
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=starts_body((kept, 5, 2), (fresh, 1, 1)))

    refresher = refresher_for(app, handler, chat_url='http://chat:8005')
    await refresher.refresh()

    # 받은 것으로 통째로 바뀐다(빠진 것은 지워진다). 주소가 없는 story 는 부르지 않아 그대로다
    assert await stored(session) == sorted(
        [('character', uuid.UUID(kept), 5, 2), ('character', uuid.UUID(fresh), 1, 1), ('world', uuid.UUID(world), 1, 1)]
    )
    path = STARTS_PATHS[WorkKind.CHARACTER]
    assert [str(request.url) for request in seen] == [f'http://chat:8005{path}']
    header = seen[0].headers[SIGNATURE_HEADER]
    assert is_valid(TEST_SECRETS['chat'], header, 'GET', path, b'', datetime.now(UTC).timestamp())


def unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError('no route')


@pytest.mark.parametrize(
    'answer',
    [
        lambda request: httpx.Response(503, json={'detail': 'down'}),
        lambda request: httpx.Response(200, json={'items': 'not a list'}),
        unreachable,
    ],
)
async def test_a_failed_fetch_keeps_the_old_counts(app: FastAPI, session: AsyncSession, answer):
    work = str(uuid.uuid4())
    await seed(session, WorkKind.WORLD, (work, 3, 2))

    refresher = refresher_for(app, answer, story_url='http://story:8007')
    assert await refresher.refresh_one(refresher.sources[0]) is False

    assert await stored(session) == [('world', uuid.UUID(work), 3, 2)]


async def test_no_address_fetches_nothing(app: FastAPI):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError('부르지 않아야 한다')

    refresher = refresher_for(app, handler)
    assert refresher.sources == []
    await refresher.run(stop=asyncio.Event())


def test_an_address_needs_its_secret():
    with pytest.raises(ValidationError, match='CHAT_SERVER_SECRET'):
        make_test_settings(chat_url='http://chat:8005', chat_server_secret='')
    with pytest.raises(ValidationError, match='STORY_SERVER_SECRET'):
        make_test_settings(story_url='http://story:8007', story_server_secret='')


# --- 랭킹 ---


async def test_characters_are_ranked_by_recent_starts(
    client: AsyncClient, session: AsyncSession, operator: dict, adult: dict
):
    first = await make_public(client, operator, name='첫째', tags=['남성향'])
    second = await make_public(client, operator, name='둘째', tags=['여성향'])
    tie = await make_public(client, operator, name='같은 수')
    quiet = await make_public(client, operator, name='지난주만')
    night = await make_public(client, operator, name='밤', rating='adult')
    hidden = await make_public(client, operator, name='비공개로 돌림')
    await client.patch(f'{CHARACTERS_URL}/{hidden["id"]}', json={'visibility': 'private'}, headers=operator)
    await seed(
        session,
        WorkKind.CHARACTER,
        (first['id'], 10, 8),
        (second['id'], 30, 5),
        (tie['id'], 6, 5),
        (quiet['id'], 50, 0),
        (night['id'], 9, 9),
        (hidden['id'], 99, 99),
        (str(uuid.uuid4()), 7, 7),
    )

    # 최근의 수가 많은 것부터, 같으면 모든 수가 많은 것부터다. 0, 비공개, 없는 작품은 빠진다. 성인용은 성인만 본다
    assert await ranked(client, 'characters') == [(1, '첫째', 8), (2, '둘째', 5), (3, '같은 수', 5)]
    assert await ranked(client, 'characters', adult) == [
        (1, '밤', 9),
        (2, '첫째', 8),
        (3, '둘째', 5),
        (4, '같은 수', 5),
    ]
    # 보는 사람의 설정(#986, #987)과 개수
    assert await ranked(client, 'characters', adult, hide_adult='true', limit=2) == [(1, '첫째', 8), (2, '둘째', 5)]
    assert await ranked(client, 'characters', adult, orientation='female') == [(1, '둘째', 5)]
    body = (await client.get(f'{RANKINGS_URL}/characters')).json()
    assert body['recent_days'] == 7
    assert datetime.fromisoformat(body['refreshed_at']) == NOW


async def test_worlds_are_ranked_and_empty_before_any_fetch(
    client: AsyncClient, session: AsyncSession, signing_key: SigningKey
):
    owner = bearer(signing_key, OWNER)
    assert (await client.get(f'{RANKINGS_URL}/worlds')).json() == {'recent_days': 7, 'refreshed_at': None, 'items': []}

    summer = await published(client, owner, name='여름')
    winter = await published(client, owner, name='겨울')
    await seed(session, WorkKind.WORLD, (summer['id'], 2, 1), (winter['id'], 4, 3))

    assert await ranked(client, 'worlds') == [(1, '겨울', 3), (2, '여름', 1)]


@pytest.mark.parametrize('params', [{'limit': 0}, {'limit': 21}, {'orientation': 'both'}])
async def test_rejects_a_bad_query(client: AsyncClient, params: dict):
    response = await client.get(f'{RANKINGS_URL}/characters', params=params)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 카드의 수와 인기순(#985) ---


async def test_refresh_copies_totals_to_the_cards(app: FastAPI, client: AsyncClient, operator: dict):
    busy = await make_public(client, operator, name='바쁜 세라')
    quiet = await make_public(client, operator, name='조용한 세라')
    answers = [starts_body((busy['id'], 12_345, 3), (quiet['id'], 2, 0)), starts_body((busy['id'], 12_346, 4))]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answers.pop(0))

    refresher = refresher_for(app, handler, chat_url='http://chat:8005')

    async def counts() -> dict[str, int]:
        return {item['name']: item['start_count'] for item in (await client.get(CHARACTER_LISTINGS)).json()['items']}

    assert await counts() == {'바쁜 세라': 0, '조용한 세라': 0}
    await refresher.refresh()
    assert await counts() == {'바쁜 세라': 12_345, '조용한 세라': 2}
    # 다음에 받은 것에 없으면 0 으로 돌아간다. 소개에도 실린다
    await refresher.refresh()
    assert await counts() == {'바쁜 세라': 12_346, '조용한 세라': 0}
    assert (await client.get(f'{CHARACTER_LISTINGS}/{busy["id"]}')).json()['start_count'] == 12_346


async def test_listings_sort_by_popularity(
    client: AsyncClient, session: AsyncSession, operator: dict, signing_key: SigningKey
):
    await make_public(client, operator, name='새것')
    week = await make_public(client, operator, name='이번 주')
    old = await make_public(client, operator, name='지난 일')
    await seed(session, WorkKind.CHARACTER, (week['id'], 2, 2), (old['id'], 50, 0))
    owner = bearer(signing_key, OWNER)
    first = await published(client, owner, name='첫 여름')
    await published(client, owner, name='둘째 여름')
    await seed(session, WorkKind.WORLD, (first['id'], 1, 1))

    async def names(url: str, **params) -> list[str]:
        response = await client.get(url, params=params)
        assert response.status_code == status.HTTP_200_OK, response.text
        return [item['name'] for item in response.json()['items']]

    # 기본은 최근에 게시한 것부터다. 인기순은 최근 7일의 수, 같으면 모든 수, 그것도 같으면 최근에 게시한 것이다
    assert await names(CHARACTER_LISTINGS) == ['지난 일', '이번 주', '새것']
    assert await names(CHARACTER_LISTINGS, sort='popular') == ['이번 주', '지난 일', '새것']
    assert await names(CHARACTER_LISTINGS, sort='popular', limit=1, offset=1) == ['지난 일']
    assert await names(WORLD_LISTINGS, sort='popular') == ['첫 여름', '둘째 여름']
    bad = await client.get(CHARACTER_LISTINGS, params={'sort': 'best'})
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
