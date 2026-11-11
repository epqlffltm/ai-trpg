# auth-server/config/db_timeouts.py

"""
DB 가 시간 한도(config/db_limits.py)로 끊은 요청을 503 으로 답한다(#1282). FastAPI 서버들의 get_session 과 같은 뜻이다.

    55P03  lock_timeout 이 지났다(잠금을 기다리다 그만뒀다)
    57014  statement_timeout 이 지났다(쿼리가 끊겼다)

그 쿼리는 적히지 않았다(트랜잭션이 되돌려졌다). 잠시 뒤 다시 보내면 된다. 그래서 503 과 Retry-After: 1 이다.
다른 DB 오류(접속 실패, 제약 위반 등)는 건드리지 않는다. 지금처럼 500 으로 간다.

미들웨어의 process_exception 에 둔다. DRF 뷰가 처리하지 못한 예외도 DRF 가 다시 던지므로 여기로 온다.
관리자 화면(/admin/)과 JWKS 도 같다. 관리자 화면도 같은 JSON 을 받는다(운영자만 본다).
미들웨어가 스스로 DB 를 읽다가 걸린 것은 오지 않는다(Django 가 그 자리에서 500 으로 바꾼다).
세션과 사용자는 뷰 안에서 처음 읽으므로 보통은 뷰 안에서 걸린다.
"""

import logging

from django.db import DatabaseError
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)

# DB 가 시간 한도로 쿼리를 끊었을 때의 오류 코드(SQLSTATE). server-core 와 결제 서버가 보는 것과 같다
LOCK_NOT_AVAILABLE = '55P03'
QUERY_CANCELED = '57014'
TIMEOUT_CODES = frozenset({LOCK_NOT_AVAILABLE, QUERY_CANCELED})
# 로그의 오류 코드(server-core 와 같다)와 응답 본문의 code(이 서버의 이름 짓는 법)
DB_TIMEOUT_ERROR_CODE = 'db.timeout'
DB_TIMEOUT_CODE = 'db_timeout'
RETRY_AFTER_SECONDS = '1'
BUSY_DETAIL = '지금은 처리할 수 없습니다. 잠시 뒤에 다시 시도해 주세요.'


def sqlstate_of(error: BaseException) -> str | None:
    """Django 의 DB 오류가 감싼 드라이버(psycopg) 오류의 코드. Django 는 원래 오류를 __cause__ 에 둔다."""
    return getattr(error.__cause__, 'sqlstate', None)


def is_db_timeout(error: BaseException) -> bool:
    """DB 가 시간 한도(잠금, 쿼리)로 끊은 오류인가."""
    return isinstance(error, DatabaseError) and sqlstate_of(error) in TIMEOUT_CODES


def busy_response() -> JsonResponse:
    """한도에 걸렸을 때의 응답. 무엇이 걸렸는지는 응답에 싣지 않는다."""
    response = JsonResponse({'detail': BUSY_DETAIL, 'code': DB_TIMEOUT_CODE}, status=503)
    response['Retry-After'] = RETRY_AFTER_SECONDS
    return response


class DbTimeoutMiddleware:
    """뷰에서 올라온 시간 한도의 오류를 503 으로 바꾼다. 다른 예외는 그대로 둔다."""

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        return self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> JsonResponse | None:
        """한도의 오류면 503 을 돌려준다. 아니면 None 이라 Django 가 지금처럼 처리한다."""
        if not is_db_timeout(exception):
            return None
        logger.warning(
            'DB 가 시간 한도로 쿼리를 끊었다',
            extra={'error_code': DB_TIMEOUT_ERROR_CODE, 'sqlstate': sqlstate_of(exception)},
        )
        return busy_response()
