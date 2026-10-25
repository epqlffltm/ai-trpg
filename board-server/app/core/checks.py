# board-server/app/core/checks.py

"""
요청의 칸을 검사하는 도구. 글의 본문(CreatePostDto 같은 것)과 주소의 값(?page=, ?q=)이 함께 쓴다.

NestJS 로 쓰던 때(class-validator, class-transformer)와 같은 결과를 내려고 따로 만들었다.
화면은 errors 의 칸 이름과 문장을 그대로 보여 준다. 그래서 무엇을 거부하는지뿐 아니라 문장의 차례까지 같아야 한다.

  - 칸마다 규칙을 그때의 검사 차례대로 적는다(Check). 걸린 규칙의 문장을 모은다
  - 같은 종류의 규칙(matches 둘)은 문장 하나로 겹친다. 자리는 처음 걸린 곳, 문장은 마지막에 걸린 것이다
  - 모르는 칸은 맨 앞에 "property 칸 should not exist" 로 알린다. 그다음이 정해 둔 칸의 차례다
  - 빈칸과 길이는 자바스크립트의 셈을 따른다(빈칸의 종류, 글자 수, Number() 로 바꾸기)

문장은 pydantic 의 오류로 낸다. 입력 오류의 본문은 app/core/errors.py 가 만든다.
"""

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError

# 자바스크립트의 \s 와 trim() 이 빈칸으로 보는 글자들
JS_SPACES = '\t\n\v\f\r                  　﻿'
SPACE = f'[{JS_SPACES}]'
NOT_SPACE = f'[^{JS_SPACES}]'

# 글자 수에서 빼는 글자(그림 글자의 모양을 고르는 글자). validator.js 의 isLength 와 같다
PRESENTATION_SELECTORS = ('️', '︎')

# Number() 가 받는 글자의 모양들
# 자바스크립트처럼 ASCII 숫자만 받는다(파이썬의 \d 와 int() 는 다른 글자의 숫자와 밑줄도 받는다)
DECIMAL = re.compile(r'\A[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\Z', re.ASCII)
INFINITY = re.compile(r'\A[+-]?Infinity\Z')
RADIX = (
    (re.compile(r'\A0[xX]([0-9a-fA-F]+)\Z'), 16),
    (re.compile(r'\A0[oO]([0-7]+)\Z'), 8),
    (re.compile(r'\A0[bB]([01]+)\Z'), 2),
)

# 오류의 종류. 문장은 그대로 나간다
ERROR_TYPE = 'board'


class Undefined:
    """보내지 않은 칸. null 과 다르다."""


UNDEFINED = Undefined()


@dataclass(frozen=True)
class Check:
    """규칙 하나. kind 가 같은 규칙은 문장 하나로 겹친다."""

    kind: str
    passes: Callable[[Any], bool]
    message: str


@dataclass(frozen=True)
class InputField:
    """
    칸 하나의 검사.

    checks 는 검사하는 차례대로다. optional 이면 null 과 보내지 않은 것은 보지 않는다.
    transform 은 검사 앞에 값을 다듬는다. convert 는 통과한 값을 모델의 타입으로 바꾼다.
    보내지 않았고 default 가 있으면 그 값으로 검사한다.
    """

    name: str
    checks: tuple[Check, ...]
    optional: bool = False
    transform: Callable[[Any], Any] | None = None
    convert: Callable[[Any], Any] | None = None
    default: Any = UNDEFINED


def js_trim(value: str) -> str:
    """자바스크립트의 trim()."""
    return value.strip(JS_SPACES)


def js_length(value: str) -> int:
    """class-validator 의 MaxLength 가 세는 글자 수."""
    return len(value) - sum(value.count(selector) for selector in PRESENTATION_SELECTORS)


def radix_number(text: str) -> float | None:
    """0x, 0o, 0b 로 시작하는 수. 그 모양이 아니면 None 이다."""
    for pattern, base in RADIX:
        found = pattern.match(text)
        if found is not None:
            return float(int(found.group(1), base))
    return None


def js_number(value: Any) -> Any:
    """
    자바스크립트의 Number(값). 주소의 값(글자)을 수로 바꾼다. 수가 아니면 NaN 이다.

    같은 이름을 여러 번 보내 목록이 된 값은 그대로 둔다. 수가 아니므로 뒤의 검사가 거부한다.
    """
    if not isinstance(value, str):
        return value
    text = js_trim(value)
    if text == '':
        return 0.0
    if INFINITY.match(text):
        return -math.inf if text.startswith('-') else math.inf
    if DECIMAL.match(text):
        return float(text)
    radix = radix_number(text)
    return math.nan if radix is None else radix


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def is_string(value: Any) -> bool:
    return isinstance(value, str)


def is_int(value: Any) -> bool:
    """Number.isInteger."""
    return is_number(value) and math.isfinite(value) and float(value).is_integer()


def at_least(minimum: int) -> Callable[[Any], bool]:
    return lambda value: is_number(value) and value >= minimum


def at_most(maximum: int) -> Callable[[Any], bool]:
    return lambda value: is_number(value) and value <= maximum


def no_longer_than(maximum: int) -> Callable[[Any], bool]:
    return lambda value: is_string(value) and js_length(value) <= maximum


def matching(pattern: re.Pattern[str]) -> Callable[[Any], bool]:
    return lambda value: is_string(value) and pattern.search(value) is not None


def to_int(value: Any) -> int:
    """검사를 통과한 수를 정수로."""
    return int(value)


def failed_messages(checks: tuple[Check, ...], value: Any) -> list[str]:
    """걸린 규칙의 문장들. 같은 종류는 처음 자리에 마지막 문장이 남는다."""
    messages: dict[str, str] = {}
    for check in checks:
        if not check.passes(value):
            messages[check.kind] = check.message
    return list(messages.values())


def unknown_field_errors(fields: tuple[InputField, ...], data: Mapping[str, Any]) -> list[tuple[str, str]]:
    """정해 두지 않은 칸들의 오류. 보낸 차례대로다."""
    known = {field.name for field in fields}
    return [(key, f'property {key} should not exist') for key in data if key not in known]


def value_of(field: InputField, data: Mapping[str, Any]) -> Any:
    """검사할 값. 보냈으면 다듬은 값, 아니면 기본값이나 UNDEFINED 다."""
    if field.name not in data:
        return field.default
    raw = data[field.name]
    return field.transform(raw) if field.transform is not None else raw


def as_validation_error(title: str, errors: list[tuple[str, str]], data: Any) -> ValidationError:
    """(칸, 문장) 들을 pydantic 의 오류 하나로. 문장은 고치지 않고 그대로 싣는다."""
    details = [
        InitErrorDetails(
            type=PydanticCustomError(ERROR_TYPE, '{message}', {'message': message}), loc=(name,), input=data
        )
        for name, message in errors
    ]
    return ValidationError.from_exception_data(title, details)


def checked(title: str, fields: tuple[InputField, ...], data: Mapping[str, Any]) -> dict[str, Any]:
    """칸들을 검사해 모델에 넘길 값을 만든다. 하나라도 걸리면 모든 오류를 한 번에 던진다."""
    errors = unknown_field_errors(fields, data)
    values: dict[str, Any] = {}
    for field in fields:
        value = value_of(field, data)
        if field.optional and (value is None or value is UNDEFINED):
            if field.name in data:
                values[field.name] = None
            continue
        messages = failed_messages(field.checks, value)
        errors.extend((field.name, message) for message in messages)
        if not messages and value is not UNDEFINED:
            values[field.name] = field.convert(value) if field.convert is not None else value
    if errors:
        raise as_validation_error(title, errors, data)
    return values


class CheckedInput(BaseModel):
    """
    input_fields 의 검사를 거쳐 만드는 요청 모델의 부모. 모르는 칸은 받지 않는다.

    검사는 칸의 타입을 보기 전에 한다. 타입이 틀린 값도 정해 둔 문장으로 알린다.
    """

    model_config = ConfigDict(extra='forbid')

    input_fields: ClassVar[tuple[InputField, ...]] = ()

    @model_validator(mode='wrap')
    @classmethod
    def check_fields(cls, data: Any, handler: Callable[[Any], Any]) -> Any:
        if not isinstance(data, Mapping):
            return handler(data)
        return handler(checked(cls.__name__, cls.input_fields, data))
