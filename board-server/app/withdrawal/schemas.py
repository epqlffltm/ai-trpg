# board-server/app/withdrawal/schemas.py

"""
탈퇴의 알림의 본문(WithdrawalDto)과 답(WithdrawalResponse).

인증 서버(auth-server/accounts/withdrawal_client.py)가 보내는 본문:

    {"withdrawn_at": "2026-10-28T03:00:00.123456+00:00"}

  - 지우는 일은 이 값을 쓰지 않는다. 검사만 한다
  - 빠졌거나 ISO 8601 이 아니거나 시간대가 없는 시각이면 400 이다. 모르는 칸도 400 이다
  - 검사와 문장은 NestJS 로 쓰던 때(class-validator 의 IsISO8601({strict: true}) 와 Matches)와 같다.
    문장의 차례도 같다: 모르는 칸이 먼저, 그다음 withdrawn_at 의 "시간대" 문장, "ISO 8601" 문장이다
"""

import re
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError

# 받은 결과. 늘 processed 다
WITHDRAWAL_PROCESSED = 'processed'

# 오류의 종류. 문장은 그대로 나간다(app/core/errors.py)
ERROR_TYPE = 'board'

FIELD = 'withdrawn_at'
NOT_ISO_MESSAGE = 'withdrawn_at 은 ISO 8601 시각이어야 합니다.'
NO_OFFSET_MESSAGE = 'withdrawn_at 에 시간대가 있어야 합니다.'

# validator.js(13.x)의 isISO8601 이 쓰는 모양을 그대로 옮겼다. 자바스크립트와 다른 곳만 바꿨다.
#   - 자바스크립트의 \d 는 ASCII 숫자뿐이고 $ 는 글의 끝이다. 그래서 re.ASCII 와 \Z 다
#     (파이썬의 $ 는 끝의 줄바꿈 앞에서도 맞는다)
#   - 자바스크립트의 \s 는 유니코드의 빈칸도 포함한다. 그래서 JS_SPACE 로 적는다
#   - 자바스크립트는 잡히지 않은 묶음을 가리키면(\17) 빈 글과 맞는다. 파이썬은 맞지 않아서 (?(17)\17) 로 적는다
# 자바스크립트의 \s 가 빈칸으로 보는 글자들
JS_SPACE = r'\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'
ISO8601 = re.compile(
    r'^([\+-]?\d{4}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W([0-4]\d|5[0-3])(-?[1-7])?'
    r'|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[1-6])))([T' + JS_SPACE + r']((([01]\d|2[0-3])((:?)[0-5]\d)?|24:?00)'
    r'([\.,]\d+(?!:))?)?((?(17)\17)[0-5]\d([\.,]\d+)?)?([zZ]|([\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?\Z',
    re.ASCII,
)
# strict 일 때 날짜가 정말 있는 날인지 보는 데 쓰는 모양(validator.js 의 isValidDate)
ORDINAL_DATE = re.compile(r'^(\d{4})-?(\d{3})([ T]{1}\.*|\Z)', re.ASCII)
CALENDAR_DATE = re.compile(r'(\d{4})-?(\d{0,2})-?(\d*)', re.ASCII)
# 시각의 끝에 시간대가 있는가(Z 나 +09:00). 인증 서버는 늘 붙인다
WITH_OFFSET = re.compile(r'(Z|[+-]\d{2}:\d{2})\Z', re.ASCII)

# 이보다 작은 해는 자바스크립트의 Date 가 "60-02-29" 같은 글로 받아 다른 해로 읽는다. 그래서 늘 있는 날이 아니다
JS_FOUR_DIGIT_YEAR = 100

DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def is_leap_year(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def is_real_date(text: str) -> bool:
    """ISO 8601 의 모양을 통과한 글의 날짜가 있는 날인가(2026-02-30 은 아니다). validator.js 와 같은 셈이다."""
    ordinal = ORDINAL_DATE.match(text)
    if ordinal is not None:
        return int(ordinal[2]) <= (366 if is_leap_year(int(ordinal[1])) else 365)
    calendar = CALENDAR_DATE.search(text)
    if calendar is None:
        return True
    year, month, day = (int(part) if part else 0 for part in calendar.groups())
    if not month or not day:
        return True
    if year < JS_FOUR_DIGIT_YEAR:
        return False
    if month > len(DAYS_IN_MONTH):
        return False
    last_day = 29 if month == 2 and is_leap_year(year) else DAYS_IN_MONTH[month - 1]
    return day <= last_day


def is_iso8601(value: Any) -> bool:
    """class-validator 의 IsISO8601({strict: true}). 글자가 아니면 아니다."""
    return isinstance(value, str) and ISO8601.match(value) is not None and is_real_date(value)


def has_offset(value: Any) -> bool:
    """class-validator 의 Matches(WITH_OFFSET). 글자가 아니면 아니다."""
    return isinstance(value, str) and WITH_OFFSET.search(value) is not None


def unknown_field_errors(data: Mapping[str, Any]) -> list[tuple[str, str]]:
    """정해 두지 않은 칸들의 오류. 보낸 차례대로다."""
    return [(str(key), f'property {key} should not exist') for key in data if key != FIELD]


def withdrawn_at_errors(data: Mapping[str, Any]) -> list[tuple[str, str]]:
    """withdrawn_at 의 오류. 보내지 않았거나 null 이어도 검사한다(NestJS 때와 같다)."""
    value = data.get(FIELD)
    errors: list[tuple[str, str]] = []
    if not has_offset(value):
        errors.append((FIELD, NO_OFFSET_MESSAGE))
    if not is_iso8601(value):
        errors.append((FIELD, NOT_ISO_MESSAGE))
    return errors


def as_validation_error(errors: list[tuple[str, str]], data: Any) -> ValidationError:
    """(칸, 문장) 들을 pydantic 의 오류 하나로. 문장은 고치지 않고 그대로 싣는다."""
    details = [
        InitErrorDetails(
            type=PydanticCustomError(ERROR_TYPE, '{message}', {'message': message}), loc=(name,), input=data
        )
        for name, message in errors
    ]
    return ValidationError.from_exception_data('WithdrawalDto', details)


class WithdrawalDto(BaseModel):
    """인증 서버가 보내는 탈퇴의 알림."""

    model_config = ConfigDict(extra='forbid')

    withdrawn_at: str = Field(description='인증 서버가 계정을 비운 시각(ISO 8601, 시간대 포함)')

    @model_validator(mode='wrap')
    @classmethod
    def check_fields(cls, data: Any, handler: Callable[[Any], Any]) -> Any:
        """칸의 타입을 보기 전에 검사한다. 하나라도 걸리면 모든 오류를 한 번에 던진다."""
        if not isinstance(data, Mapping):
            return handler(data)
        errors = unknown_field_errors(data) + withdrawn_at_errors(data)
        if errors:
            raise as_validation_error(errors, data)
        return handler(data)


class WithdrawalResponse(BaseModel):
    """탈퇴를 받은 답. 인증 서버는 processed 를 받아야 보내기를 멈춘다."""

    # 기본값을 두지 않는다. 두면 API 목록에서 적지 않아도 되는 칸이 된다(NestJS 로 쓰던 때는 꼭 있는 칸이었다)
    status: Literal['processed'] = Field(description='반영했다. 이미 했거나 할 것이 없었던 것도 같다')
