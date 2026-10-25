# board-server/tests/test_posts_search.py

"""
글 검색(app/posts/search.py)에서 HTTP 만으로 볼 수 없는 것을 검증한다. 주소와 응답의 시나리오는 계약 시험이 본다.

  - 시간 제한에 걸린 검색은 503 이고, 결과 timeout 과 걸린 시간을 센다
  - 걸린 뒤의 연결도 그대로 쓴다(제한은 그 트랜잭션에만 걸린다)
  - 시간 제한이 아닌 DB 의 오류는 감추지 않는다(503 으로 바꾸지 않는다)
  - 끝까지 간 검색은 success 다
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.metrics import MetricsRecorder
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.posts import repository, search

POSTS = '/api/v1/board/posts'
FREE_POSTS = '/api/v1/board/boards/free/posts'

pytestmark = pytest.mark.usefixtures('clean_tables')

Headers = Callable[..., dict[str, str]]


async def slow_search(session: AsyncSession, *args: object, **kwargs: object):
    """시간 제한보다 오래 걸리는 검색."""
    await session.execute(text('SELECT pg_sleep(1)'))
    raise AssertionError('시간 제한에 걸려야 한다')


async def broken_search(session: AsyncSession, *args: object, **kwargs: object):
    """시간 제한이 아닌 이유로 실패하는 검색."""
    await session.execute(text('SELECT 1 / 0'))
    raise AssertionError('0 으로 나누면 실패해야 한다')


async def test_a_search_that_takes_too_long_is_503(
    client: AsyncClient, metrics: MetricsRecorder, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(search, 'SEARCH_TIMEOUT_MS', 50)
    monkeypatch.setattr(repository, 'search', slow_search)

    response = await client.get(POSTS, params={'q': '주사위'})

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {'detail': '검색이 오래 걸려 멈췄습니다. 검색어를 바꿔 다시 시도해 주세요.'}
    assert metrics.value('board_searches', result='timeout') == 1
    assert metrics.value('board_search_duration') == 1


async def test_the_connection_works_after_a_timeout(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    with monkeypatch.context() as patched:
        patched.setattr(search, 'SEARCH_TIMEOUT_MS', 50)
        patched.setattr(repository, 'search', slow_search)
        await client.get(POSTS, params={'q': '주사위'})

    response = await client.get(POSTS, params={'q': '주사위'})

    assert response.status_code == status.HTTP_200_OK


async def test_other_database_errors_are_not_hidden(session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(repository, 'search', broken_search)

    with pytest.raises(DBAPIError):
        await search.find_page(session, ['주사위'], None, 1, 20)


async def test_a_finished_search_is_success(client: AsyncClient, headers_for: Headers, metrics: MetricsRecorder):
    writer = headers_for(str(uuid.uuid4()))
    created = await client.post(FREE_POSTS, headers=writer, json={'title': '주사위 이야기', 'content': '본문'})
    assert created.status_code == status.HTTP_201_CREATED

    response = await client.get(POSTS, params={'q': '주사위', 'board': 'free'})

    assert [item['id'] for item in response.json()['items']] == [created.json()['id']]
    assert metrics.value('board_searches', result='success') == 1
