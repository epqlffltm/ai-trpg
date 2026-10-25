# board-server/app/posts/search.py

"""
글을 검색한다. 읽기만 한다.

모든 게시판에서 찾는 것이 기본이고, 게시판 하나로 좁히는 것은 고르는 값(board)이다.
결과는 글 목록과 같은 모양이다. 고정한 글을 따로 싣지 않는다. 찾은 글을 새 글부터 보여 줄 뿐이다.

검색 하나가 DB 를 오래 붙잡지 못하게 시간 제한을 건다. 넘으면 DB 가 쿼리를 멈추고, 503 으로 답한다.
검색은 로그인 없이 부른다. 누가 얼마나 부르는지를 세는 것은 프록시의 일이다. 여기서는 한 번의 값만 묶어 둔다.

검색마다 결과(success, timeout)와 걸린 시간을 센다(board_searches_total, board_search_duration_seconds).
timeout 이 늘면 색인이나 검색 엔진이 필요하다. 그 밖의 실패(DB 가 없다)는 세지 않는다. 요청의 5xx 로 보인다.
"""

import time
from collections.abc import Sequence

from fastapi import status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.boards import service as boards
from app.core.errors import ApiError
from app.core.metrics import SEARCH_SUCCESS, SEARCH_TIMEOUT, record_search
from app.posts import policy, repository
from app.posts.repository import SummaryRows
from app.posts.schemas import PostSummaryPageResponse, SearchPostsQuery
from app.posts.service import board_by_slug, summary_responses
from app.posts.terms import terms_of

# 검색 쿼리에 주는 시간(천분의 1초). 넘으면 DB 가 쿼리를 멈춘다
SEARCH_TIMEOUT_MS = 3000
# PostgreSQL 이 시간 제한(statement_timeout)으로 쿼리를 멈췄을 때의 오류 코드
QUERY_CANCELED = '57014'


def search_took_too_long() -> ApiError:
    """검색이 시간 제한에 걸렸을 때의 응답. 원인(쿼리, 걸린 시간)은 싣지 않는다."""
    return ApiError(
        status.HTTP_503_SERVICE_UNAVAILABLE, '검색이 오래 걸려 멈췄습니다. 검색어를 바꿔 다시 시도해 주세요.'
    )


def is_statement_timeout(error: DBAPIError) -> bool:
    """이 오류는 DB 가 시간 제한으로 쿼리를 멈춘 것인가."""
    driver_error = error.orig
    code = getattr(driver_error, 'sqlstate', None) or getattr(driver_error, 'pgcode', None)
    return code == QUERY_CANCELED


async def find_page(
    session: AsyncSession, terms: Sequence[str], board_id: int | None, page: int, size: int
) -> tuple[SummaryRows, int]:
    """
    낱말이 모두 들어 있는 글 한 쪽과 전체 개수. 시간 제한을 건 채로 찾는다. 넘기면 503 이다.

    제한은 이 트랜잭션에만 걸린다(SET LOCAL). 찾은 뒤 트랜잭션을 끝내 뒤의 쿼리(댓글 수, 닉네임)에는 걸리지 않게 한다.
    """
    started = time.perf_counter()
    try:
        await repository.limit_statement_time(session, SEARCH_TIMEOUT_MS)
        found = await repository.search(session, terms, board_id, policy.offset_of(page, size), size)
        await session.commit()
    except DBAPIError as error:
        await session.rollback()
        if not is_statement_timeout(error):
            raise
        record_search(SEARCH_TIMEOUT, time.perf_counter() - started)
        raise search_took_too_long() from error
    record_search(SEARCH_SUCCESS, time.perf_counter() - started)
    return found


async def board_slugs(session: AsyncSession, board_id: int | None, board_slug: str | None) -> dict[int, str]:
    """게시판의 번호로 이름을 찾는 표. 게시판 하나에서 찾았으면 그 게시판만이다."""
    if board_id is not None and board_slug is not None:
        return {board_id: board_slug}
    return {board.id: board.slug for board in await boards.list_boards(session)}


async def search_posts(session: AsyncSession, query: SearchPostsQuery) -> PostSummaryPageResponse:
    """
    낱말이 모두 들어 있는 글을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. 없는 게시판이면 404 다.
    지운 글은 나오지 않는다. 고정한 글은 다른 글과 같이 제 번호의 자리에 나온다.
    """
    now = policy.current_time()
    board = None if query.board is None else await board_by_slug(session, query.board)
    # 시간 제한에 걸리면 트랜잭션을 되돌린다. 읽어 둔 게시판의 값은 그 전에 꺼내 둔다
    board_id, board_slug = (None, None) if board is None else (board.id, board.slug)
    rows, total = await find_page(session, terms_of(query.q), board_id, query.page, query.size)
    slugs = await board_slugs(session, board_id, board_slug)
    items = await summary_responses(session, rows, slugs, now)
    return PostSummaryPageResponse(items=items, page=query.page, size=query.size, total=total)
