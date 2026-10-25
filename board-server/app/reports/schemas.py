# board-server/app/reports/schemas.py

"""
신고 API 가 받는 값과 내보내는 응답의 모양.

받는 값의 검사는 문장과 차례가 NestJS 로 쓰던 때와 같다(app/core/checks.py).
  - 모르는 칸이 먼저, 그다음이 사유, 설명의 차례다
  - 설명은 적지 않아도 된다. 다만 기타(other)를 고르면 꼭 적는다. 적었다면 빈칸만 적을 수는 없다
  - 설명의 검사는 한 함수(description_problem)에 모았다. 틀린 까닭 하나만 알린다.
    설명을 적지 않았을 때 "글자여야 합니다", "500자를 넘을 수 없습니다"까지 한꺼번에 나오면 무엇이 틀렸는지 흐려진다

응답의 칸 이름은 밑줄로 잇고, 번호는 글자로 내보낸다. 글, 댓글과 같다.
신고한 사람에게는 접수했다는 것만 돌려준다. 누가 무엇을 신고했는지(설명, 신고한 사람)는 운영자의 응답에만 싣는다.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from app.core.checks import (
    UNDEFINED,
    Check,
    CheckedInput,
    InputField,
    as_validation_error,
    failed_messages,
    is_string,
    matching,
    no_longer_than,
    unknown_field_errors,
)
from app.core.times import Timestamp
from app.posts.schemas import HAS_VISIBLE_TEXT, NO_NUL, ListPostsQuery
from app.reports.models import Report
from app.reports.policy import (
    DESCRIPTION_MAX_LENGTH,
    REPORT_OUTCOMES,
    REPORT_REASONS,
    OutcomeName,
    ReasonName,
    needs_description,
)
from app.reports.targets import ReportTarget, TargetState, TargetType

DESCRIPTION_REQUIRED_MESSAGE = '기타(other)를 고르면 설명을 적어야 합니다.'
DESCRIPTION_NOT_STRING_MESSAGE = '설명은 글자여야 합니다.'
DESCRIPTION_BLANK_MESSAGE = '설명을 적어야 합니다.'
DESCRIPTION_NUL_MESSAGE = '설명에 쓸 수 없는 글자가 있습니다.'
DESCRIPTION_TOO_LONG_MESSAGE = f'설명은 {DESCRIPTION_MAX_LENGTH}자를 넘을 수 없습니다.'


def one_of(values: tuple[str, ...]) -> Callable[[Any], bool]:
    """정해 둔 값 가운데 하나인가(class-validator 의 IsIn)."""
    return lambda value: is_string(value) and value in values


REASON_CHECKS = (
    Check('isIn', one_of(REPORT_REASONS), f'reason 은 {", ".join(REPORT_REASONS)} 가운데 하나여야 합니다.'),
)
OUTCOME_CHECKS = (
    Check('isIn', one_of(REPORT_OUTCOMES), f'outcome 은 {", ".join(REPORT_OUTCOMES)} 가운데 하나여야 합니다.'),
)
# 신고할 때 받는 칸. 모르는 칸을 가리는 데 쓴다. 설명의 검사는 description_problem 이 한다
REPORT_FIELDS = (InputField('reason', REASON_CHECKS), InputField('description', (), optional=True))


def description_problem(reason: object, description: object) -> str | None:
    """
    설명이 왜 틀렸는지 돌려준다. 맞으면 None 이다.
    받은 설명은 문장에 넣지 않는다. 오류 응답과 로그에 신고의 설명이 실리지 않게 한다.
    """
    if description is None or description is UNDEFINED:
        return DESCRIPTION_REQUIRED_MESSAGE if needs_description(reason) else None
    if not is_string(description):
        return DESCRIPTION_NOT_STRING_MESSAGE
    if not matching(HAS_VISIBLE_TEXT)(description):
        return DESCRIPTION_BLANK_MESSAGE
    if not matching(NO_NUL)(description):
        return DESCRIPTION_NUL_MESSAGE
    # 글과 댓글의 길이 검사와 같은 셈으로 센다
    if not no_longer_than(DESCRIPTION_MAX_LENGTH)(description):
        return DESCRIPTION_TOO_LONG_MESSAGE
    return None


def checked_report(title: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """신고의 칸들을 검사해 모델에 넘길 값을 만든다. 하나라도 걸리면 모든 오류를 한 번에 던진다."""
    errors = unknown_field_errors(REPORT_FIELDS, data)
    reason = data.get('reason', UNDEFINED)
    errors.extend(('reason', message) for message in failed_messages(REASON_CHECKS, reason))
    description = data.get('description', UNDEFINED)
    problem = description_problem(reason, description)
    if problem is not None:
        errors.append(('description', problem))
    if errors:
        raise as_validation_error(title, errors, data)
    return {'reason': reason, 'description': None if description is UNDEFINED else description}


# 받는 값


class CreateReportDto(CheckedInput):
    """신고할 때 받는 값. 무엇을 신고하는지는 주소에 있고, 신고한 사람은 토큰에서 안다."""

    reason: ReasonName = Field(description='사유')
    description: str | None = Field(
        default=None, description='설명. 받은 그대로 저장한다. 적지 않거나 null 이면 설명이 없는 것이다'
    )

    @model_validator(mode='wrap')
    @classmethod
    def check_fields(cls, data: Any, handler: Callable[[Any], Any]) -> Any:
        """설명의 규칙이 사유에 달려 있어서 칸마다의 검사(CheckedInput) 대신 신고의 검사를 쓴다."""
        if not isinstance(data, Mapping):
            return handler(data)
        return handler(checked_report(cls.__name__, data))


class HandleReportsDto(CheckedInput):
    """운영자가 신고를 처리할 때 받는 값."""

    input_fields: ClassVar[tuple[InputField, ...]] = (InputField('outcome', OUTCOME_CHECKS),)

    outcome: OutcomeName = Field(description='처리한 결과. 조치함(actioned), 문제없음(dismissed)')


class ListReportsQuery(ListPostsQuery):
    """신고 목록을 부를 때 주소에 붙이는 값(?page=2&size=20). 글 목록과 같다."""


# 응답


class ReportReceiptResponse(BaseModel):
    """신고한 사람에게 돌려주는 것. 접수했다는 표시다."""

    id: str
    reason: ReasonName
    created_at: Timestamp


class ReportResponse(BaseModel):
    """운영자가 읽는 신고 한 건."""

    id: str
    reason: ReasonName
    description: str | None = Field(description='신고한 사람이 붙인 설명. 적지 않았으면 null')
    reporter_id: str | None = Field(description='신고한 사람. 인증 서버의 public_id. 탈퇴한 사람이면 null 이다')
    created_at: Timestamp
    handled_at: Timestamp | None = Field(description='처리한 시각. 열린 신고면 null')
    handled_by: str | None = Field(description='처리한 운영자. 열린 신고면 null')
    outcome: OutcomeName | None = Field(description='처리한 결과. 열린 신고면 null')


class ReportTargetResponse(BaseModel):
    """신고당한 것. 운영자의 목록에서 무엇에 걸린 신고인지 보여 준다."""

    type: TargetType
    id: str
    post_id: str = Field(description='글이면 그 글의 번호, 댓글이면 그 댓글이 달린 글의 번호')
    deleted: bool = Field(description='지금 지워져 있는가. 지운 것에 걸린 신고도 처리해서 닫아야 목록에서 빠진다')


class ReasonCountsResponse(BaseModel):
    """사유마다의 건수. 사유가 없었던 것도 0 으로 실린다."""

    spam: int
    abuse: int
    sexual: int
    illegal: int
    other: int


class OpenReportGroupResponse(BaseModel):
    """운영자의 목록 한 줄. 신고당한 것 하나에 걸린 열린 신고들이다."""

    target: ReportTargetResponse
    open_count: int
    reasons: ReasonCountsResponse
    first_reported_at: Timestamp
    last_reported_at: Timestamp


class ReportPageResponse(BaseModel):
    """한 글이나 댓글에 걸린 신고 목록의 한 쪽."""

    items: list[ReportResponse]
    page: int = Field(description='몇 번째 쪽인가. 1 부터 센다')
    size: int = Field(description='한 쪽에 몇 개를 담는가')
    total: int = Field(description='전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다')


class OpenReportGroupPageResponse(BaseModel):
    """열린 신고 목록의 한 쪽."""

    items: list[OpenReportGroupResponse]
    page: int = Field(description='몇 번째 쪽인가. 1 부터 센다')
    size: int = Field(description='한 쪽에 몇 개를 담는가')
    total: int = Field(description='전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다')


@dataclass(frozen=True)
class OpenReportGroup:
    """신고당한 것 하나에 걸린 열린 신고들. DB 가 묶어 센 한 줄이다."""

    target: ReportTarget
    open_count: int
    # 사유마다의 수. 모든 사유가 있다
    reasons: dict[str, int]
    first_reported_at: datetime
    last_reported_at: datetime


def to_report_receipt_response(report_id: int, reason: str, created_at: datetime) -> ReportReceiptResponse:
    return ReportReceiptResponse(id=str(report_id), reason=reason, created_at=created_at)  # type: ignore[arg-type]


def to_report_response(report: Report) -> ReportResponse:
    return ReportResponse(
        id=str(report.id),
        reason=report.reason,  # type: ignore[arg-type]
        description=report.description,
        reporter_id=None if report.reporter_id is None else str(report.reporter_id),
        created_at=report.created_at,
        handled_at=report.handled_at,
        handled_by=None if report.handled_by is None else str(report.handled_by),
        outcome=report.outcome,  # type: ignore[arg-type]
    )


def to_report_target_response(target: ReportTarget, state: TargetState) -> ReportTargetResponse:
    return ReportTargetResponse(type=target.type, id=str(target.id), post_id=str(state.post_id), deleted=state.deleted)


def to_open_report_group_response(group: OpenReportGroup, state: TargetState) -> OpenReportGroupResponse:
    return OpenReportGroupResponse(
        target=to_report_target_response(group.target, state),
        open_count=group.open_count,
        reasons=ReasonCountsResponse(**group.reasons),
        first_reported_at=group.first_reported_at,
        last_reported_at=group.last_reported_at,
    )
