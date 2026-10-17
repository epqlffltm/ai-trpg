# auth-server/accounts/origin_check.py

"""
refresh 쿠키를 쓰는 요청이 우리 화면에서 왔는지 Origin 머리말로 본다.

refresh 와 logout 은 쿠키만 보고 동작한다. 다른 곳의 페이지가 이 주소로 요청을 보내게 만들면
브라우저가 쿠키를 실어 보낸다. SameSite=Strict 는 다른 사이트를 막지만, 같은 사이트의 다른 하위 도메인
(예: 다른 서비스가 쓰는 chat.example.com)에서 온 요청은 막지 못한다. 그래서 출처를 허용 목록과 직접 비교한다.

브라우저는 fetch 와 폼의 POST 에 Origin 을 늘 붙인다. 없거나 "null"(파일, 샌드박스 iframe, 일부 리다이렉트)이면
어디서 왔는지 알 수 없으므로 통과시키지 않는다. 브라우저 밖의 도구(curl)는 Origin 을 직접 적어 보내야 한다.
"""

import logging

from django.conf import settings
from django.http import HttpRequest

logger = logging.getLogger(__name__)

# 출처를 알 수 없다는 뜻으로 브라우저가 보내는 값
NULL_ORIGIN = 'null'

# 로그에 남기는 Origin 의 최대 길이. 보내는 쪽이 마음대로 적는 값이라 길이를 자른다
LOGGED_ORIGIN_LENGTH = 100


def read_origin(request: HttpRequest) -> str | None:
    """요청의 Origin 을 소문자로 돌려준다. 없거나 "null" 이면 None."""
    origin = request.META.get('HTTP_ORIGIN', '').strip().lower()
    if not origin or origin == NULL_ORIGIN:
        return None
    return origin


def is_allowed_origin(origin: str | None) -> bool:
    """허용 목록(REFRESH_COOKIE_ALLOWED_ORIGINS)에 그대로 있는 출처인가. 앞뒤 일부만 맞는 것은 아니다."""
    return origin is not None and origin in settings.REFRESH_COOKIE_ALLOWED_ORIGINS


def log_refused_origin(origin: str | None, path: str) -> None:
    """
    출처 때문에 거부한 요청을 로그에 남긴다.

    DB 의 보안 이벤트로는 남기지 않는다. 누구나 마음대로 일으킬 수 있어, 요청 수만큼 행이 쌓인다.
    값은 길이를 자르고 repr 로 적는다. 줄바꿈 같은 글자로 로그 줄을 꾸며 넣지 못한다.
    """
    shown = None if origin is None else origin[:LOGGED_ORIGIN_LENGTH]
    logger.warning('허용하지 않은 출처의 쿠키 요청을 거부했다. path=%s origin=%r', path, shown)
