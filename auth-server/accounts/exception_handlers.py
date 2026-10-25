# auth-server/accounts/exception_handlers.py

"""
뷰에서 올라온 예외를 응답으로 바꾼다. DRF 의 기본 처리에 시도 횟수 제한과 입력 오류의 본문을 더한다.

제한에 걸리는 길은 둘이다.
  - throttle 이 막는다: DRF 가 Throttled 를 낸다.
  - 뷰가 부른 정책 함수가 막는다: TooManyAttemptsError 가 올라온다.
어느 쪽이든 같은 429 응답이 나가게 여기서 맞춘다. 뷰마다 try/except 를 적지 않아도 된다.

입력 오류(칸의 검증, 400)는 서버들이 함께 쓰는 본문으로 바꾼다(docs/api/README.md 의 "오류의 모양").

    {"detail": "입력이 올바르지 않습니다.", "errors": {"username": ["..."]}}

DRF 의 기본({"username": [...]})은 칸 이름이 맨 위에 펼쳐져서 detail 이 없고, 입력 칸의 이름(code 등)이
오류의 이름(code)과 부딪친다. 화면은 errors 칸이 있는지로 입력 오류를 알아본다. 상태 코드(400)는 그대로다.
"""

import math
from datetime import timedelta
from typing import Any

from rest_framework import status
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler

from accounts.attempt_limits import TooManyAttemptsError

# 입력이 틀렸을 때의 문장. 어느 칸이 왜 틀렸는지는 errors 에 싣는다. 다른 서버들과 같은 문장이다
INVALID_INPUT_DETAIL = '입력이 올바르지 않습니다.'


def handle_exception(exc: Exception, context: dict) -> Response | None:
    """
    예외에 맞는 응답을 돌려준다. settings 의 EXCEPTION_HANDLER 에 등록되어 있다.

    시도 횟수 제한이 아니면 DRF 의 기본 처리에 넘기고, 입력 오류면 본문을 공통 모양으로 바꾼다.
    """
    if isinstance(exc, TooManyAttemptsError):
        return build_too_many_attempts_response(exc.retry_after)
    if isinstance(exc, Throttled):
        return build_too_many_attempts_response(timedelta(seconds=exc.wait or 0))
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, ValidationError):
        response.data = input_error_body(response.data)
    return response


def input_error_body(field_errors: Any) -> dict[str, Any]:
    """
    DRF 가 만든 칸마다의 오류를 공통 본문으로 감싼다.

    칸을 가르지 않는 오류(목록으로 온 것)는 non_field_errors 칸에 둔다. DRF 가 serializer 에서 쓰는 이름과 같다.
    """
    errors = field_errors if isinstance(field_errors, dict) else {api_settings.NON_FIELD_ERRORS_KEY: field_errors}
    return {'detail': INVALID_INPUT_DETAIL, 'errors': errors}


def build_too_many_attempts_response(retry_after: timedelta) -> Response:
    """
    시도 횟수 제한에 걸렸을 때의 응답.

    무엇을 기준으로 셌는지(IP 인지 계정인지), 몇 번까지인지는 알려 주지 않는다.
    기다릴 시간만 본문과 Retry-After 머리말에 초 단위로 싣는다. 올림해서, 그 시간 뒤에는 반드시 되게 한다.
    """
    seconds = max(1, math.ceil(retry_after.total_seconds()))
    response = Response(
        {
            'detail': '시도가 너무 많습니다. 잠시 뒤에 다시 시도해 주세요.',
            'code': 'too_many_attempts',
            'retry_after': seconds,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response['Retry-After'] = str(seconds)
    return response
