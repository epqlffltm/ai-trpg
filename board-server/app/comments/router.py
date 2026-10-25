# board-server/app/comments/router.py

"""
댓글의 API. 주소를 받아 서비스를 부르고, 결과를 돌려준다.

    GET    /posts/{postId}/comments   한 글의 댓글 목록(답글 포함)    로그인 불필요
    POST   /posts/{postId}/comments   댓글 쓰기, 답글 쓰기            로그인 필요
    PATCH  /comments/{id}             댓글 고치기(글쓴이)             로그인 필요
    DELETE /comments/{id}             댓글 지우기(글쓴이, 운영자)     로그인 필요

쓰기는 글 아래에 둔다. 댓글은 글에 다는 것이다. 답글도 같은 주소로 쓰고, 어느 댓글에 다는지를
본문(parent_id)으로 알린다. 고치고 지울 때는 댓글 번호만으로 가리킨다.

로그인이 필요한 주소는 토큰을 먼저 본다(401). 그다음이 주소의 번호의 모양(404), 본문의 검사(400) 차례다.
본문이 JSON 이 아니면 그 모든 것보다 먼저 400 이다(본문을 읽는 단계다. NestJS 로 쓰던 때도 같았다).
쓰기, 고치기, 지우기는 결과마다 센다(board_writes_total).
"""

from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.comments import service
from app.comments.schemas import (
    CommentListResponse,
    CommentResponse,
    CreateCommentDto,
    ListCommentsQuery,
    UpdateCommentDto,
    record_id_of,
)
from app.core.auth import Member
from app.core.dependencies import Session
from app.core.ids import parse_record_id
from app.core.metrics import counted, record_write
from app.core.query_params import query_model, query_parameters
from app.posts.service import post_not_found

router = APIRouter(tags=['comments'])


def post_id_in_path(post_id: Annotated[str, Path(alias='postId')]) -> int:
    """주소의 글 번호. 번호의 모양이 아니면 그런 글이 없는 것이다(404)."""
    parsed = parse_record_id(post_id)
    if parsed is None:
        raise post_not_found()
    return parsed


def comment_id_in_path(comment_id: Annotated[str, Path(alias='id')]) -> int:
    """주소의 댓글 번호. 번호의 모양이 아니면 그런 댓글이 없는 것이다(404)."""
    parsed = parse_record_id(comment_id)
    if parsed is None:
        raise service.comment_not_found()
    return parsed


PostId = Annotated[int, Depends(post_id_in_path)]
CommentId = Annotated[int, Depends(comment_id_in_path)]
ListQuery = Annotated[ListCommentsQuery, Depends(query_model(ListCommentsQuery))]


@router.get(
    '/posts/{postId}/comments',
    response_model=CommentListResponse,
    status_code=status.HTTP_200_OK,
    openapi_extra=query_parameters(ListCommentsQuery),
)
async def list_comments(post_id: PostId, query: ListQuery, session: Session) -> CommentListResponse:
    """한 글의 댓글을 한 토막 돌려준다. 먼저 쓴 것부터고, 댓글마다 답글이 모두 붙어 있다."""
    return await service.list_comments(session, post_id, record_id_of(query.after), query.size)


@router.post('/posts/{postId}/comments', response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(actor: Member, post_id: PostId, data: CreateCommentDto, session: Session) -> CommentResponse:
    """글에 댓글을 단다. parent_id 를 적으면 그 댓글에 답글을 단다. 쓴 댓글을 돌려준다."""
    with counted(partial(record_write, 'comment', 'create')):
        return await service.create_comment(session, post_id, actor, data.content, record_id_of(data.parent_id))


@router.patch('/comments/{id}', response_model=CommentResponse, status_code=status.HTTP_200_OK)
async def update_comment(
    actor: Member, comment_id: CommentId, data: UpdateCommentDto, session: Session
) -> CommentResponse:
    """댓글의 내용을 고친다. 고친 댓글을 돌려준다."""
    with counted(partial(record_write, 'comment', 'update')):
        return await service.update_comment(session, comment_id, actor, data.content)


@router.delete('/comments/{id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(actor: Member, comment_id: CommentId, session: Session) -> None:
    """댓글을 지운다. 돌려줄 내용이 없다."""
    with counted(partial(record_write, 'comment', 'delete')):
        await service.delete_comment(session, comment_id, actor)
