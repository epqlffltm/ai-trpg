# board-server/app/posts/schemas.py

"""
글 API 가 받는 값과 내보내는 응답의 모양.

받는 값의 검사는 칸마다 규칙을 적어 둔다(app/posts/checks.py). 문장과 차례가 NestJS 로 쓰던 때와 같다.
  - 제목은 앞뒤 빈칸을 떼고 저장한다. 본문은 받은 그대로다. 줄바꿈과 들여쓰기가 글의 일부다
  - 빈칸만 적은 글과 NUL 글자는 받지 않는다. PostgreSQL 의 글자 칸은 NUL 을 담지 못한다
  - 검색어는 빈칸으로 낱말을 나눈다. 낱말마다 두 글자 이상, 다섯 낱말까지, 모두 50자까지다

응답의 칸 이름은 다른 서버들처럼 밑줄로 잇는다(author_id). 글 번호는 글자로 내보낸다.
글쓴이가 탈퇴했으면 ID 와 닉네임이 null 이고 author_withdrawn 이 true 다. 화면은 "탈퇴한 사용자"로 그린다.
목록에는 본문을 싣지 않는다. 댓글 수와 닉네임은 글의 칸이 아니다. 따로 읽어서 넘겨받는다.
고정되어 있는지는 지금 시각에 달려 있다. 끝나는 시각이 지난 글은 고정하지 않은 글로 내보낸다.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Protocol

from pydantic import BaseModel, Field

from app.boards.service import BOARD_SLUG
from app.core.checks import (
    NOT_SPACE,
    Check,
    CheckedInput,
    InputField,
    at_least,
    at_most,
    is_int,
    is_string,
    js_number,
    js_trim,
    matching,
    no_longer_than,
    to_int,
)
from app.core.times import Timestamp
from app.posts import policy
from app.posts.terms import (
    MAX_QUERY_LENGTH,
    MAX_TERMS,
    MIN_TERM_LENGTH,
    NOT_TOO_MANY_TERMS,
    TERMS_LONG_ENOUGH,
    normalize_query,
)

# 빈칸이 아닌 글자가 하나는 있다
HAS_VISIBLE_TEXT = re.compile(NOT_SPACE)
# NUL 글자가 없다
NO_NUL = re.compile(r'\A[^\x00]*\Z')


def trim_text(value: object) -> object:
    """글자면 앞뒤 빈칸을 뗀다. 글자가 아니면 그대로 둔다. 그것은 뒤의 검사가 거부한다."""
    return js_trim(value) if isinstance(value, str) else value


def text_checks(label: str, max_length: int) -> tuple[Check, ...]:
    """제목과 본문의 규칙. 검사하는 차례대로다(길이, NUL, 빈칸, 글자인가)."""
    return (
        Check('maxLength', no_longer_than(max_length), f'{label}은 {max_length}자를 넘을 수 없습니다.'),
        Check('matches', matching(NO_NUL), f'{label}에 쓸 수 없는 글자가 있습니다.'),
        Check('matches', matching(HAS_VISIBLE_TEXT), f'{label}을 적어야 합니다.'),
        Check('isString', is_string, f'{label}은 글자여야 합니다.'),
    )


def number_checks(name: str, minimum: int, maximum: int) -> tuple[Check, ...]:
    """정수 칸의 규칙. 검사하는 차례대로다(가장 큰 값, 가장 작은 값, 정수인가)."""
    return (
        Check('max', at_most(maximum), f'{name} 는 {maximum} 이하여야 합니다.'),
        Check('min', at_least(minimum), f'{name} 는 {minimum} 이상이어야 합니다.'),
        Check('isInt', is_int, f'{name} 는 정수여야 합니다.'),
    )


TITLE_CHECKS = text_checks('제목', policy.TITLE_MAX_LENGTH)
CONTENT_CHECKS = text_checks('본문', policy.CONTENT_MAX_LENGTH)

# 쪽을 나누는 값. 주소의 글자를 수로 바꿔(Number()) 검사한다
PAGE_FIELDS = (
    InputField(
        'page',
        number_checks('page', 1, policy.MAX_PAGE),
        transform=js_number,
        convert=to_int,
        default=policy.DEFAULT_PAGE,
    ),
    InputField(
        'size',
        number_checks('size', 1, policy.MAX_PAGE_SIZE),
        transform=js_number,
        convert=to_int,
        default=policy.DEFAULT_PAGE_SIZE,
    ),
)

# 검색어. 다듬은 뒤에 검사한다(길이, NUL, 낱말의 수, 낱말의 길이, 글자인가)
QUERY_FIELD = InputField(
    'q',
    (
        Check('maxLength', no_longer_than(MAX_QUERY_LENGTH), f'검색어는 {MAX_QUERY_LENGTH}자를 넘을 수 없습니다.'),
        Check('matches', matching(NO_NUL), '검색어에 쓸 수 없는 글자가 있습니다.'),
        Check('matches', matching(NOT_TOO_MANY_TERMS), f'검색어의 낱말은 {MAX_TERMS}개를 넘을 수 없습니다.'),
        Check('matches', matching(TERMS_LONG_ENOUGH), f'검색어는 낱말마다 {MIN_TERM_LENGTH}자 이상이어야 합니다.'),
        Check('isString', is_string, 'q 는 글자여야 합니다.'),
    ),
    transform=normalize_query,
)

# 찾을 게시판. 적지 않으면 모든 게시판에서 찾는다
BOARD_FIELD = InputField(
    'board',
    (
        Check('matches', matching(BOARD_SLUG), 'board 는 게시판의 이름이어야 합니다.'),
        Check('isString', is_string, 'board 는 글자여야 합니다.'),
    ),
    optional=True,
)


# 받는 값


class CreatePostDto(CheckedInput):
    """글을 쓸 때 받는 값. 어느 게시판인지는 주소에 있고, 글쓴이는 토큰에서 안다."""

    input_fields: ClassVar[tuple[InputField, ...]] = (
        InputField('title', TITLE_CHECKS, transform=trim_text),
        InputField('content', CONTENT_CHECKS),
    )

    title: str = Field(
        description='제목. 앞뒤 빈칸은 떼고 저장한다', json_schema_extra={'maxLength': policy.TITLE_MAX_LENGTH}
    )
    content: str = Field(
        description='본문. 받은 그대로 저장한다. 줄바꿈과 들여쓰기가 글의 일부다',
        json_schema_extra={'maxLength': policy.CONTENT_MAX_LENGTH},
    )


class UpdatePostDto(CheckedInput):
    """
    글을 고칠 때 받는 값. 고칠 칸만 보낸다. 보내지 않은 칸은 그대로 둔다. 칸마다의 규칙은 쓸 때와 같다.

    null 을 보낸 칸은 보낸 칸으로 치지만 고치지 않는다(NestJS 로 쓰던 때와 같다).
    """

    input_fields: ClassVar[tuple[InputField, ...]] = (
        InputField('title', TITLE_CHECKS, optional=True, transform=trim_text),
        InputField('content', CONTENT_CHECKS, optional=True),
    )

    title: str | None = Field(default=None, json_schema_extra={'maxLength': policy.TITLE_MAX_LENGTH})
    content: str | None = Field(default=None, json_schema_extra={'maxLength': policy.CONTENT_MAX_LENGTH})


class PinPostDto(CheckedInput):
    """글을 고정할 때 받는 값. 본문 없이 불러도 된다."""

    input_fields: ClassVar[tuple[InputField, ...]] = (
        InputField(
            'days', number_checks('days', 1, policy.MAX_PIN_DAYS), convert=to_int, default=policy.DEFAULT_PIN_DAYS
        ),
    )

    days: int = Field(
        default=policy.DEFAULT_PIN_DAYS,
        ge=1,
        le=policy.MAX_PIN_DAYS,
        description='며칠 동안 고정하는가. 적지 않으면 7일이다. 그날이 지나면 저절로 내려간다',
    )


class ListPostsQuery(CheckedInput):
    """글 목록을 부를 때 주소에 붙이는 값(?page=2&size=20)."""

    input_fields: ClassVar[tuple[InputField, ...]] = PAGE_FIELDS

    page: int = Field(default=policy.DEFAULT_PAGE, ge=1, le=policy.MAX_PAGE, description='몇 번째 쪽인가. 1 부터 센다')
    size: int = Field(
        default=policy.DEFAULT_PAGE_SIZE, ge=1, le=policy.MAX_PAGE_SIZE, description='한 쪽에 몇 개를 담는가'
    )


class SearchPostsQuery(ListPostsQuery):
    """글을 검색할 때 주소에 붙이는 값(?q=고정+버그&board=free&page=1&size=20). 오류는 검색어의 칸부터 알린다."""

    input_fields: ClassVar[tuple[InputField, ...]] = (QUERY_FIELD, BOARD_FIELD, *PAGE_FIELDS)

    q: str = Field(
        description='검색어. 빈칸으로 낱말을 나눈다. 모든 낱말이 제목이나 본문에 들어 있는 글을 찾는다',
        json_schema_extra={'maxLength': MAX_QUERY_LENGTH},
    )
    board: str | None = Field(
        default=None, description='어느 게시판에서 찾는가. 주소 이름(slug)이다. 적지 않으면 모든 게시판에서 찾는다'
    )


# 응답


class PostSummaryResponse(BaseModel):
    """글 목록의 한 줄."""

    id: str
    board: str = Field(description='글이 있는 게시판의 주소 이름(slug)')
    author_id: str | None = Field(description='글쓴이. 탈퇴한 사람이면 null 이다')
    author_nickname: str | None = Field(
        description='글쓴이의 닉네임. 이 서버가 이름을 모르는 사람이거나 탈퇴한 사람이면 null 이다'
    )
    author_withdrawn: bool = Field(description='글쓴이가 탈퇴했는가')
    title: str
    comment_count: int = Field(description='살아 있는 댓글과 답글의 수. 지운 것은 세지 않는다')
    pinned: bool = Field(description='지금 고정되어 있는가')
    pinned_until: Timestamp | None = Field(description='고정이 끝나는 시각. 고정되어 있지 않으면 null 이다')
    created_at: Timestamp
    updated_at: Timestamp


class PostResponse(PostSummaryResponse):
    """글 하나. 목록의 한 줄에 본문이 더해진다."""

    content: str


class PostSummaryPageResponse(BaseModel):
    """글 목록의 한 쪽. 검색의 결과가 이 모양이다."""

    items: list[PostSummaryResponse]
    page: int = Field(description='몇 번째 쪽인가. 1 부터 센다')
    size: int = Field(description='한 쪽에 몇 개를 담는가')
    total: int = Field(description='전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다')


class PostListResponse(PostSummaryPageResponse):
    """게시판의 글 목록의 한 쪽. 고정한 글을 따로 싣는다."""

    pinned: list[PostSummaryResponse] = Field(
        description='지금 고정되어 있는 글들. 나중에 고정한 것부터다. 첫 쪽에만 싣는다. items 와 total 에는 들지 않는다'
    )


class PostSummary(Protocol):
    """목록에 싣는 데 필요한 글의 칸들. 글의 행이나 일부 칸만 읽은 줄이다."""

    id: int
    board_id: int
    author_id: uuid.UUID | None
    title: str
    pinned_until: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PostContext:
    """글의 칸이 아니어서 따로 넘겨받는 것들."""

    board_slug: str
    comment_count: int
    author_nickname: str | None
    now: datetime


def to_post_summary_response(post: PostSummary, context: PostContext) -> PostSummaryResponse:
    return PostSummaryResponse(
        id=str(post.id),
        board=context.board_slug,
        author_id=None if post.author_id is None else str(post.author_id),
        author_nickname=context.author_nickname,
        author_withdrawn=post.author_id is None,
        title=post.title,
        comment_count=context.comment_count,
        pinned=policy.is_pinned(post.pinned_until, context.now),
        pinned_until=policy.pinned_until_of(post.pinned_until, context.now),
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


def to_post_response(post: PostSummary, content: str, context: PostContext) -> PostResponse:
    summary = to_post_summary_response(post, context)
    return PostResponse(**summary.model_dump(), content=content)
