# board-server/app/comments/schemas.py

"""
댓글 API 가 받는 값과 내보내는 응답의 모양.

받는 값의 검사는 칸마다 규칙을 적어 둔다(app/core/checks.py). 문장과 차례가 NestJS 로 쓰던 때와 같다.
  - 내용은 받은 그대로 저장한다. 빈칸만 적은 댓글과 NUL 글자는 받지 않는다. 규칙은 글의 본문과 같다
  - 번호(parent_id, after)는 글자로 받는다("57"). 번호의 모양이 아니면 400 이다

응답의 칸 이름은 밑줄로 잇고, 번호는 글자로 내보낸다. 글과 같다.
지운 댓글은 답글이 달려 있을 때만 목록에 나온다. 그때는 자리만 보여 준다.
누가 무엇을 썼는지(author_id, author_nickname, content)는 비우고 deleted 를 true 로 둔다.
글쓴이가 탈퇴했으면 ID 와 닉네임이 null 이고 author_withdrawn 이 true 다.
지운 댓글은 누가 썼는지 보이지 않으므로 false 다.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Protocol

from pydantic import BaseModel, Field

from app.comments import policy
from app.core.checks import Check, CheckedInput, InputField, is_string, js_number, matching, to_int
from app.core.ids import record_id
from app.core.times import Timestamp
from app.posts.schemas import number_checks, text_checks

# 번호의 모양. 자바스크립트의 /^[1-9]\d{0,17}$/ 와 같다(ASCII 숫자만, 끝의 줄바꿈도 받지 않는다)
RECORD_ID = re.compile(r'\A[1-9][0-9]{0,17}\Z')

CONTENT_FIELD = InputField('content', text_checks('댓글', policy.COMMENT_MAX_LENGTH))


def record_id_of(value: str | None) -> int | None:
    """검사를 통과한 번호의 글자를 수로. 적지 않았으면 None 이다."""
    return None if value is None else int(value)


# 받는 값


class CreateCommentDto(CheckedInput):
    """댓글을 쓸 때 받는 값. 어느 글인지는 주소에 있고, 글쓴이는 토큰에서 안다."""

    input_fields: ClassVar[tuple[InputField, ...]] = (
        CONTENT_FIELD,
        InputField(
            'parent_id',
            (
                Check('matches', matching(RECORD_ID), 'parent_id 는 댓글 번호여야 합니다.'),
                Check('isString', is_string, 'parent_id 는 글자로 적은 댓글 번호여야 합니다.'),
            ),
            optional=True,
        ),
    )

    content: str = Field(
        description='내용. 받은 그대로 저장한다', json_schema_extra={'maxLength': policy.COMMENT_MAX_LENGTH}
    )
    parent_id: str | None = Field(
        default=None,
        description=(
            '답글이면 어느 댓글에 다는가. 적지 않거나 null 이면 글에 다는 댓글이다. 번호는 글자로 보낸다("57").\n'
            'null 을 받는 것은 화면이 "답글이 아님"을 null 로 보내기 쉬워서다'
        ),
    )


class UpdateCommentDto(CheckedInput):
    """댓글을 고칠 때 받는 값. 고칠 수 있는 것은 내용뿐이다. 어느 글, 어느 댓글에 달린 것인지는 옮길 수 없다."""

    input_fields: ClassVar[tuple[InputField, ...]] = (CONTENT_FIELD,)

    content: str = Field(json_schema_extra={'maxLength': policy.COMMENT_MAX_LENGTH})


class ListCommentsQuery(CheckedInput):
    """댓글 목록을 부를 때 주소에 붙이는 값(?after=57&size=20)."""

    input_fields: ClassVar[tuple[InputField, ...]] = (
        InputField(
            'after',
            (Check('matches', matching(RECORD_ID), 'after 는 댓글 번호여야 합니다.'),),
            optional=True,
        ),
        InputField(
            'size',
            number_checks('size', 1, policy.MAX_SLICE_SIZE),
            transform=js_number,
            convert=to_int,
            default=policy.DEFAULT_SLICE_SIZE,
        ),
    )

    after: str | None = Field(
        default=None,
        description='이 번호의 댓글 다음부터 읽는다. 적지 않으면 처음부터다. 앞의 응답의 next 를 그대로 넣는다',
    )
    size: int = Field(
        default=policy.DEFAULT_SLICE_SIZE,
        ge=1,
        le=policy.MAX_SLICE_SIZE,
        description='한 번에 댓글을 몇 개 담는가. 답글은 세지 않는다',
    )


# 응답


class CommentResponse(BaseModel):
    """댓글 하나."""

    id: str
    post_id: str
    parent_id: str | None = Field(description='답글이면 어느 댓글에 단 것인가. 글에 단 댓글이면 null')
    author_id: str | None = Field(description='글쓴이. 지운 댓글이거나 탈퇴한 사람이면 null')
    author_nickname: str | None = Field(
        description='글쓴이의 닉네임. 지운 댓글이거나, 이 서버가 이름을 모르는 사람이거나, 탈퇴한 사람이면 null'
    )
    author_withdrawn: bool = Field(description='글쓴이가 탈퇴했는가. 지운 댓글이면 false 다')
    content: str | None = Field(description='내용. 지운 댓글이면 null')
    deleted: bool = Field(description='지운 댓글인가. 답글이 달려 있어 자리만 남은 것이다')
    created_at: Timestamp
    updated_at: Timestamp


class CommentThreadResponse(CommentResponse):
    """목록의 한 줄. 글에 단 댓글 하나와 거기 달린 답글들이다."""

    replies: list[CommentResponse]


class CommentListResponse(BaseModel):
    """댓글 목록의 한 토막."""

    items: list[CommentThreadResponse]
    next: str | None = Field(description='다음 토막을 부를 때 after 에 넣을 값. 뒤에 더 없으면 null 이다')


class CommentFields(Protocol):
    """응답에 싣는 데 필요한 댓글의 칸들. 댓글의 행이나 고친 뒤의 값이다."""

    id: int
    post_id: int
    parent_id: int | None
    author_id: uuid.UUID | None
    content: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class CommentThread:
    """글에 단 댓글 하나와 거기 달린 답글들."""

    comment: CommentFields
    replies: list[CommentFields]


def threads_of(comments: Sequence[CommentFields], replies: Sequence[CommentFields]) -> list[CommentThread]:
    """
    댓글마다 제 답글을 붙인다. 댓글의 차례와 답글의 차례는 받은 그대로 둔다.
    어느 댓글의 것도 아닌 답글은 버린다. 답글이 없는 댓글은 빈 목록을 갖는다.
    """
    by_parent: dict[int, list[CommentFields]] = {comment.id: [] for comment in comments}
    for reply in replies:
        if reply.parent_id in by_parent:
            by_parent[reply.parent_id].append(reply)
    return [CommentThread(comment=comment, replies=by_parent[comment.id]) for comment in comments]


def nickname_in(nicknames: dict[uuid.UUID, str], author_id: uuid.UUID | None) -> str | None:
    """표에서 글쓴이의 닉네임. 비운 글쓴이와 모르는 사람은 None 이다."""
    return None if author_id is None else nicknames.get(author_id)


def to_comment_response(comment: CommentFields, nicknames: dict[uuid.UUID, str]) -> CommentResponse:
    deleted = comment.deleted_at is not None
    return CommentResponse(
        id=str(comment.id),
        post_id=str(comment.post_id),
        parent_id=record_id(comment.parent_id),
        author_id=None if deleted or comment.author_id is None else str(comment.author_id),
        author_nickname=None if deleted else nickname_in(nicknames, comment.author_id),
        author_withdrawn=not deleted and comment.author_id is None,
        content=None if deleted else comment.content,
        deleted=deleted,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


def to_thread_response(thread: CommentThread, nicknames: dict[uuid.UUID, str]) -> CommentThreadResponse:
    return CommentThreadResponse(
        **to_comment_response(thread.comment, nicknames).model_dump(),
        replies=[to_comment_response(reply, nicknames) for reply in thread.replies],
    )


def authors_of(threads: Sequence[CommentThread]) -> list[uuid.UUID | None]:
    """댓글들(답글 포함)을 쓴 사람들. 지운 댓글은 뺀다. 이름을 읽을 사람들이다."""
    return [
        comment.author_id
        for thread in threads
        for comment in (thread.comment, *thread.replies)
        if comment.deleted_at is None
    ]
