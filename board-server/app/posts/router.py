# board-server/app/posts/router.py

"""
글의 API. 주소를 받아 서비스를 부르고, 결과를 돌려준다.

    GET    /boards/{slug}/posts   한 게시판의 글 목록(쪽 번호). 첫 쪽에 고정한 글   로그인 불필요
    POST   /boards/{slug}/posts   글 쓰기                                           로그인 필요
    GET    /posts?q=&board=       글 검색                                           로그인 불필요
    GET    /posts/{id}            글 읽기                                           로그인 불필요
    PATCH  /posts/{id}            글 고치기(글쓴이)                                 로그인 필요
    DELETE /posts/{id}            글 지우기(글쓴이, 운영자)                         로그인 필요
    PUT    /posts/{id}/pin        글 고정(본문의 days, 적지 않으면 7일)             운영자
    DELETE /posts/{id}/pin        글 고정 풀기                                      운영자

쓰기는 게시판 아래에 둔다. 읽고 고치고 지울 때는 글 번호만으로 가리킨다. 글 번호는 게시판마다 따로 세지 않는다.
고정은 고치기와 주소를 따로 둔다. 고치는 것은 글쓴이만, 고정하는 것은 운영자만 한다. 둘 다 여러 번 불러도 결과가 같다.

주소의 모양부터 본다. 게시판 이름이나 글 번호의 모양이 아니면 DB 에 묻지 않고 404 다.
로그인이 필요한 주소는 토큰을 먼저 본다(401). 그다음이 주소의 모양, 본문의 검사(400) 차례다.
본문이 JSON 이 아니면 그 모든 것보다 먼저 400 이다(본문을 읽는 단계다. NestJS 로 쓰던 때도 같았다).
쓰기, 고치기, 지우기는 결과마다 센다(board_writes_total).
"""

from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.boards import service as boards
from app.core.auth import FOR_OPERATORS, Member
from app.core.dependencies import Session
from app.core.ids import parse_record_id
from app.core.metrics import counted, record_write
from app.core.query_params import query_model, query_parameters
from app.posts import search, service
from app.posts.schemas import (
    CreatePostDto,
    ListPostsQuery,
    PinPostDto,
    PostListResponse,
    PostResponse,
    PostSummaryPageResponse,
    SearchPostsQuery,
    UpdatePostDto,
)

router = APIRouter(tags=['posts'])


def post_id_in_path(post_id: Annotated[str, Path(alias='id')]) -> int:
    """주소의 글 번호. 번호의 모양이 아니면 그런 글이 없는 것이다(404)."""
    parsed = parse_record_id(post_id)
    if parsed is None:
        raise service.post_not_found()
    return parsed


def board_slug_in_path(slug: str) -> str:
    """주소의 게시판 이름. 이름의 모양이 아니면 그런 게시판이 없는 것이다(404)."""
    boards.ensure_board_slug(slug)
    return slug


PostId = Annotated[int, Depends(post_id_in_path)]
BoardSlug = Annotated[str, Depends(board_slug_in_path)]
ListQuery = Annotated[ListPostsQuery, Depends(query_model(ListPostsQuery))]
SearchQuery = Annotated[SearchPostsQuery, Depends(query_model(SearchPostsQuery))]


@router.get(
    '/boards/{slug}/posts',
    response_model=PostListResponse,
    status_code=status.HTTP_200_OK,
    openapi_extra=query_parameters(ListPostsQuery),
)
async def list_posts(slug: BoardSlug, query: ListQuery, session: Session) -> PostListResponse:
    """한 게시판의 글 목록을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. 첫 쪽에는 고정한 글을 따로 싣는다."""
    return await service.list_posts(session, slug, query.page, query.size)


@router.post('/boards/{slug}/posts', response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(actor: Member, slug: BoardSlug, data: CreatePostDto, session: Session) -> PostResponse:
    """게시판에 글을 쓴다. 쓴 글을 돌려준다."""
    with counted(partial(record_write, 'post', 'create')):
        return await service.create_post(session, slug, actor, data)


@router.get(
    '/posts',
    response_model=PostSummaryPageResponse,
    status_code=status.HTTP_200_OK,
    openapi_extra=query_parameters(SearchPostsQuery),
)
async def search_posts(query: SearchQuery, session: Session) -> PostSummaryPageResponse:
    """낱말이 모두 들어 있는 글을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. 없는 게시판이면 404 다."""
    return await search.search_posts(session, query)


@router.get('/posts/{id}', response_model=PostResponse, status_code=status.HTTP_200_OK)
async def read_post(post_id: PostId, session: Session) -> PostResponse:
    """글 하나를 본문까지 돌려준다."""
    return await service.read_post(session, post_id)


@router.patch('/posts/{id}', response_model=PostResponse, status_code=status.HTTP_200_OK)
async def update_post(actor: Member, post_id: PostId, data: UpdatePostDto, session: Session) -> PostResponse:
    """글을 고친다. 보낸 칸만 고친다. 고친 글을 돌려준다."""
    with counted(partial(record_write, 'post', 'update')):
        return await service.update_post(session, post_id, actor, data)


@router.delete('/posts/{id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(actor: Member, post_id: PostId, session: Session) -> None:
    """글을 지운다. 돌려줄 내용이 없다."""
    with counted(partial(record_write, 'post', 'delete')):
        await service.delete_post(session, post_id, actor)


@router.put('/posts/{id}/pin', status_code=status.HTTP_204_NO_CONTENT, openapi_extra=FOR_OPERATORS)
async def pin_post(actor: Member, post_id: PostId, session: Session, data: PinPostDto | None = None) -> None:
    """글을 고정한다. 본문 없이 부르면 7일이다."""
    days = (data or PinPostDto()).days
    await service.pin_post(session, post_id, actor, days)


@router.delete('/posts/{id}/pin', status_code=status.HTTP_204_NO_CONTENT, openapi_extra=FOR_OPERATORS)
async def unpin_post(actor: Member, post_id: PostId, session: Session) -> None:
    """글의 고정을 푼다."""
    await service.unpin_post(session, post_id, actor)
