# board-server/app/reports/targets.py

"""
신고하는 것(글이나 댓글)을 가리키는 값. 순수한 값과 함수들이다.

글과 댓글은 같은 길(신고하기, 읽기, 처리하기)을 걷는다. 다른 것은 어느 칸(post_id, comment_id)을 보느냐뿐이다.
그 차이를 이 파일과 저장소(repository.py)의 조건 하나에 모은다. 서비스는 종류를 가리지 않고 이 값을 넘긴다.
"""

from dataclasses import dataclass
from typing import Literal

# 신고하는 것의 종류
TargetType = Literal['post', 'comment']

POST: TargetType = 'post'
COMMENT: TargetType = 'comment'


@dataclass(frozen=True)
class ReportTarget:
    """신고하는 것. 종류와 번호다."""

    type: TargetType
    id: int


@dataclass(frozen=True)
class TargetState:
    """신고당한 것의 지금 상태. 신고의 칸이 아니어서 따로 읽어 넘긴다."""

    # 글이면 그 글의 번호, 댓글이면 그 댓글이 달린 글의 번호
    post_id: int
    deleted: bool


def post_target(target_id: int) -> ReportTarget:
    return ReportTarget(POST, target_id)


def comment_target(target_id: int) -> ReportTarget:
    return ReportTarget(COMMENT, target_id)


def target_of(post_id: int | None, comment_id: int | None) -> ReportTarget:
    """신고의 두 칸에서 무엇을 가리키는지 읽는다. 둘 다 비어 있는 행은 DB 가 막는다."""
    if post_id is not None:
        return post_target(post_id)
    if comment_id is not None:
        return comment_target(comment_id)
    raise ValueError('신고가 글도 댓글도 가리키지 않는다')
