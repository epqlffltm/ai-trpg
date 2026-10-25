# board-server/app/reports/errors.py

"""
신고를 다루다 거절할 때의 응답들. 문장을 한곳에 모아 둔다. 문장은 NestJS 로 쓰던 때와 같다.

받은 설명은 어느 문장에도 넣지 않는다. 응답과 로그에 신고의 설명이 실리지 않게 한다.
"""

from fastapi import status
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApiError
from app.reports.targets import POST, TargetType

# PostgreSQL 의 오류 번호: 유일해야 하는 값이 겹쳤다
UNIQUE_VIOLATION = '23505'


def comment_not_found() -> ApiError:
    """그런 댓글이 없다. 지운 댓글과 지운 글에 달린 댓글도 없는 댓글이다(댓글 API 와 같은 문장)."""
    return ApiError(status.HTTP_404_NOT_FOUND, '댓글을 찾을 수 없습니다.')


def cannot_report_own(target_type: TargetType) -> ApiError:
    """자기 글이나 자기 댓글을 신고하려 했다."""
    detail = '자신의 글은 신고할 수 없습니다.' if target_type == POST else '자신의 댓글은 신고할 수 없습니다.'
    return ApiError(status.HTTP_403_FORBIDDEN, detail)


def already_reported() -> ApiError:
    """이미 신고했다. 같은 것을 두 번 신고하지 못한다."""
    return ApiError(status.HTTP_409_CONFLICT, '이미 신고했습니다.')


def operator_only_reports() -> ApiError:
    """운영자가 아닌 사람이 신고를 읽거나 처리하려 했다."""
    return ApiError(status.HTTP_403_FORBIDDEN, '운영자만 신고를 볼 수 있습니다.')


def no_open_reports() -> ApiError:
    """처리할 신고가 없다. 신고가 없거나 이미 모두 처리했다."""
    return ApiError(status.HTTP_404_NOT_FOUND, '처리할 신고가 없습니다.')


def is_unique_violation(error: IntegrityError) -> bool:
    """이 오류는 DB 의 유일 제약에 걸린 것인가. 같은 신고가 동시에 두 번 들어오면 늦은 쪽이 여기에 걸린다."""
    return getattr(error.orig, 'sqlstate', None) == UNIQUE_VIOLATION
