# board-server/app/reports/policy.py

"""
신고의 규칙. DB 도 FastAPI 도 모르는 순수한 값과 함수들이다.

  - 사유는 정해 둔 다섯 가운데 하나다. 운영자가 사유별로 세고 거를 수 있다.
    기타(other)를 고르면 설명을 꼭 적는다. "기타"만으로는 무엇이 문제인지 알 수 없다
  - 자기 글과 자기 댓글은 신고하지 못한다. 쓸모가 없고 운영자의 목록만 어지럽힌다
  - 같은 사람이 같은 것을 두 번 신고하지 못한다(DB 의 유일 제약이 지킨다)
  - 신고를 읽고 처리하는 것은 운영자만 한다. 누가 신고했는지는 운영자만 안다
  - 신고가 쌓여도 저절로 가리지 않는다. 여럿이 짜고 멀쩡한 글을 가릴 수 있다. 사람이 본다
"""

import uuid
from typing import Literal

from app.reports.models import ReportOutcome, ReportReason

# 신고의 사유. 스팸·광고, 욕설·괴롭힘, 음란물, 불법 정보, 기타. 운영자의 목록이 이 차례로 센다
REPORT_REASONS: tuple[str, ...] = tuple(reason.value for reason in ReportReason)
# 운영자가 처리한 결과. 조치함(글을 지우는 등), 문제없음
REPORT_OUTCOMES: tuple[str, ...] = tuple(outcome.value for outcome in ReportOutcome)

# 응답과 API 목록에 적는 타입. 위의 값과 같다
ReasonName = Literal['spam', 'abuse', 'sexual', 'illegal', 'other']
OutcomeName = Literal['actioned', 'dismissed']

# 설명의 최대 길이(글자)
DESCRIPTION_MAX_LENGTH = 500


def needs_description(reason: object) -> bool:
    """이 사유면 설명을 꼭 적어야 하는가."""
    return reason == ReportReason.OTHER.value


def can_report(author_id: uuid.UUID | None, reporter_id: uuid.UUID) -> bool:
    """이 사람이 이것(글이나 댓글)을 신고해도 되는가. 자기가 쓴 것은 안 된다. 글쓴이가 탈퇴한 것(None)은 누구나 한다."""
    return author_id != reporter_id


def can_review(is_operator: bool) -> bool:
    """신고를 읽고 처리해도 되는가. 운영자만 된다."""
    return is_operator
