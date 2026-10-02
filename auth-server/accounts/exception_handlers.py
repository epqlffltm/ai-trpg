# auth-server/accounts/exception_handlers.py

"""
뷰에서 올라온 예외를 응답으로 바꾼다. DRF 의 기본 처리에 시도 횟수 제한을 더한다.

제한에 걸리는 길은 둘이다.
  - throttle 이 막는다: DRF 가 Throttled 를 낸다.
  - 뷰가 부른 정책 함수가 막는다: TooManyAttemptsError 가 올라온다.
어느 쪽이든 같은 429 응답이 나가게 여기서 맞춘다. 뷰마다 try/except 를 적지 않아도 된다.
"""

import math
from datetime import timedelta

from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.response import Response
from rest_framework.views import exception_handler

from accounts.attempt_limits import TooManyAttemptsError


def handle_exception(exc: Exception, context: dict) -> Response | None:
    """
    예외에 맞는 응답을 돌려준다. settings 의 EXCEPTION_HANDLER 에 등록되어 있다.

    시도 횟수 제한이 아니면 DRF 의 기본 처리에 넘긴다.
    """
    if isinstance(exc, TooManyAttemptsError):
        return build_too_many_attempts_response(exc.retry_after)
    if isinstance(exc, Throttled):
        return build_too_many_attempts_response(timedelta(seconds=exc.wait or 0))
    return exception_handler(exc, context)


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
