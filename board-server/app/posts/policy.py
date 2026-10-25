# board-server/app/posts/policy.py

"""
글에 관한 규칙. DB 도 FastAPI 도 모르는 순수한 함수와 값들이다.

권한
  - 쓰기: 게시판이 정한 대로다. 공지처럼 운영자만 쓰는 게시판이 있다
  - 고치기: 글쓴이만. 운영자도 남의 글을 고치지 못한다. 남의 이름으로 글을 바꿔 쓰는 일이 된다.
    운영자만 쓰는 게시판의 글은 글쓴이가 지금도 운영자여야 고친다
  - 지우기: 글쓴이와 운영자. 운영자만 쓰는 게시판의 글은 운영자만 지운다.
    공지를 쓴 사람이 운영자에서 내려온 뒤에도 그 공지를 지울 수 있으면 안 된다
  - 읽기는 누구나 한다. 규칙이 없다

고정
  - 고정하고 푸는 것은 운영자만 한다. 글쓴이도 제 글을 고정하지 못한다
  - 고정에는 끝이 있다. 끝나는 시각이 지난 글을 고정한 글로 읽지 않을 뿐이다. 열을 비우는 작업을 따로 돌리지 않는다
  - 한 게시판에 고정할 수 있는 글의 수에 끝이 있다. 없으면 목록의 첫 쪽이 고정한 글로 덮인다

쪽 나누기는 쪽 번호 방식이다. 몇 번째 쪽(page)과 한 쪽의 개수(size)를 받고 전체 개수(total)를 함께 돌려준다.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.boards.models import Board, WritePolicy

# 제목과 본문의 최대 길이(글자). 제목은 posts.title 의 varchar 길이와 같다
TITLE_MAX_LENGTH = 100
CONTENT_MAX_LENGTH = 20000

# 쪽: 적지 않았을 때의 쪽과 개수, 가장 큰 개수, 볼 수 있는 가장 뒤의 쪽
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_PAGE = 10000

# 고정: 한 게시판에 함께 고정해 둘 수 있는 수, 적지 않았을 때의 기간(일), 가장 긴 기간(일)
MAX_PINS_PER_BOARD = 5
DEFAULT_PIN_DAYS = 7
MAX_PIN_DAYS = 365


def current_time() -> datetime:
    """지금 시각. 밀리초까지다(NestJS 로 쓰던 때의 시각과 같은 정밀도)."""
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def offset_of(page: int, size: int) -> int:
    """이 쪽의 앞에서 건너뛸 개수."""
    return (page - 1) * size


def is_operator_only(board: Board) -> bool:
    """이 게시판은 운영자만 쓰는가."""
    return board.write_policy == WritePolicy.OPERATOR


def can_write(board: Board, is_operator: bool) -> bool:
    """이 게시판에 글을 써도 되는가."""
    return not is_operator_only(board) or is_operator


def is_author(author_id: uuid.UUID | None, user_id: uuid.UUID) -> bool:
    """이 사람이 글쓴이인가. 글쓴이가 탈퇴한 글(None)은 누구의 글도 아니다."""
    return author_id == user_id


def can_edit(author_id: uuid.UUID | None, board: Board, user_id: uuid.UUID, is_operator: bool) -> bool:
    """이 글을 고쳐도 되는가. 글쓴이만이고, 운영자만 쓰는 게시판이면 지금도 운영자여야 한다."""
    if not is_author(author_id, user_id):
        return False
    return not is_operator_only(board) or is_operator


def can_delete(author_id: uuid.UUID | None, board: Board, user_id: uuid.UUID, is_operator: bool) -> bool:
    """이 글을 지워도 되는가. 글쓴이와 운영자다. 운영자만 쓰는 게시판의 글은 운영자만 지운다."""
    if is_operator_only(board):
        return is_operator
    return is_author(author_id, user_id) or is_operator


def can_pin(is_operator: bool) -> bool:
    """글을 고정하거나 풀어도 되는가. 운영자만이다."""
    return is_operator


def has_room_to_pin(others_pinned: int) -> bool:
    """이 게시판에 글을 하나 더 고정해도 되는가. others_pinned 는 이 글 말고 지금 고정되어 있는 글의 수다."""
    return others_pinned < MAX_PINS_PER_BOARD


def pin_ends_at(now: datetime, days: int) -> datetime:
    """지금 고정하면 언제 끝나는가."""
    return now + timedelta(days=days)


def is_pinned(pinned_until: datetime | None, now: datetime) -> bool:
    """지금 고정되어 있는가. 끝나는 시각이 지났으면 아니다."""
    return pinned_until is not None and pinned_until > now


def pinned_until_of(pinned_until: datetime | None, now: datetime) -> datetime | None:
    """고정이 끝나는 시각. 지금 고정되어 있지 않으면 None 이다. 지난 시각은 내보내지 않는다."""
    return pinned_until if is_pinned(pinned_until, now) else None
