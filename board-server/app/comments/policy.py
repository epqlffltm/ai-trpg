# board-server/app/comments/policy.py

"""
댓글에 관한 규칙. DB 도 FastAPI 도 모르는 순수한 함수와 값들이다.

  - 쓰기: 로그인한 누구나. 운영자만 글을 쓰는 게시판(공지사항)의 글에도 댓글은 누구나 단다
  - 답글: 글에 단 댓글에만 단다. 답글에는 달지 못한다. 한 댓글에 달 수 있는 수에 끝이 있다
  - 고치기: 글쓴이만. 지우기: 글쓴이와 운영자. 글과 같다

목록은 쪽 번호가 아니라 "이것 다음 몇 개"로 끊어 읽는다. 마지막으로 받은 댓글의 번호(after)를 주면 그다음 것들이다.
읽는 사이에 새 댓글이 달려도 같은 댓글이 두 번 나오거나 빠지지 않는다. 대신 몇 쪽으로 건너뛸 수는 없다.
더 있는지는 하나를 더 읽어 보고 안다. size 개를 달라고 하면 size + 1 개를 읽는다.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# 댓글의 최대 길이(글자)
COMMENT_MAX_LENGTH = 2000

# 한 댓글에 달 수 있는 답글의 수.
# 댓글 목록은 댓글마다 답글을 모두 실어 보낸다. 끝이 없으면 한 댓글에 답글을 쏟아부어 응답을 한없이 키울 수 있다
MAX_REPLIES_PER_COMMENT = 100

# 목록: 적지 않았을 때 한 번에 담는 개수, 한 번에 담을 수 있는 가장 큰 개수
DEFAULT_SLICE_SIZE = 20
MAX_SLICE_SIZE = 50


@dataclass(frozen=True)
class Slice[Item]:
    """목록의 한 토막. next 는 다음 토막을 부를 때 after 에 넣을 번호다. 뒤에 더 없으면 None 이다."""

    items: list[Item]
    next: int | None


def is_reply(parent_id: int | None) -> bool:
    """이 댓글은 답글인가."""
    return parent_id is not None


def can_have_replies(parent_id: int | None) -> bool:
    """이 댓글에 답글을 달 수 있는 종류인가. 글에 단 댓글에만 단다."""
    return not is_reply(parent_id)


def has_room_for_reply(reply_count: int) -> bool:
    """답글이 지금 reply_count 개 달린 댓글에 하나 더 달 자리가 있는가."""
    return reply_count < MAX_REPLIES_PER_COMMENT


def is_author(author_id: uuid.UUID | None, user_id: uuid.UUID) -> bool:
    """이 사람이 글쓴이인가. 글쓴이가 탈퇴한 댓글(None)은 누구의 것도 아니다. 고칠 수 없고 운영자만 지운다."""
    return author_id is not None and author_id == user_id


def can_edit(author_id: uuid.UUID | None, user_id: uuid.UUID) -> bool:
    """고쳐도 되는가. 글쓴이만이다. 운영자도 남의 댓글을 고치지 못한다."""
    return is_author(author_id, user_id)


def can_delete(author_id: uuid.UUID | None, user_id: uuid.UUID, is_operator: bool) -> bool:
    """지워도 되는가. 글쓴이와 운영자다."""
    return is_author(author_id, user_id) or is_operator


def fetch_count(size: int) -> int:
    """size 개를 돌려주려면 몇 개를 읽어야 하는가. 더 있는지 보려고 하나를 더 읽는다."""
    return size + 1


def slice_of[Item](fetched: Sequence[Item], size: int, id_of: Callable[[Item], int]) -> Slice[Item]:
    """읽어 온 것(size + 1 개까지)을 토막으로 묶는다. 다음 토막은 마지막 항목의 번호 뒤부터다."""
    items = list(fetched[:size])
    has_more = len(fetched) > size
    return Slice(items=items, next=id_of(items[-1]) if has_more and items else None)
