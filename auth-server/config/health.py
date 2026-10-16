# auth-server/config/health.py

"""
상태 확인 주소 둘. 다른 세 서버와 같은 뜻이다(저장소 루트의 docs/observability.md 의 "health 와 readiness").

    GET /health         프로세스가 살아 있는가. 아무것도 보지 않는다. 늘 200
    GET /health/ready   요청을 처리할 준비가 됐는가. DB 에 닿으면 200, 닿지 않으면 503

둘 다 HEAD 도 받는다(본문 없이 같은 상태 코드). 네 서버가 같다. 다른 메서드는 405 다.
요청이 끝난 줄은 성공이면 debug, 503 이면 warning 이다(observability/middleware.py 의 probe_level_of).

API 주소(/api/v1/...) 밖에 두고 로그인 없이 부른다. 컨테이너 관리 도구(compose 의 healthcheck)와 프록시가 부른다.
바깥에서는 nginx 가 이 주소들을 막는다.

readiness 에 Redis 는 넣지 않는다. 시도 횟수 제한만 쓰고, 죽어 있으면 제한 없이 통과시키도록 만들었다.
없어도 일을 하는 것은 readiness 에 넣지 않는다.

응답에는 status 하나만 싣는다. 왜 DB 에 닿지 않는지(오류의 글에는 DB 주소와 계정이 들어 있다)는 로그에만 남긴다.

결제·게시판 서버와 달리 readiness 전체에 시간 제한(3초)을 걸지 않는다. 연결 시간(settings 의
DATABASE_CONNECT_TIMEOUT_SECONDS, 5초)만 묶여 있다. 동기 Django(psycopg)에는 쿼리 하나만 시간으로 끊는 장치가 없다.
  - statement_timeout 은 DB 가 살아서 느릴 때만 듣는다. DB 가 멈췄거나 네트워크가 끊겼을 때는 듣지 않는다
  - 스레드로 떼어 놓고 기다리면 답을 늦출 수는 있지만, 멈춘 스레드는 끝나지 않고 쌓인다
확인하는 쪽은 compose 의 healthcheck 가 묶는다(timeout 5초, 지나면 실패로 센다). 그동안 이 요청이 워커를 쥐는 것은
같은 DB 앞의 보통 요청과 같다. docs/observability.md 의 "health 와 readiness" 에 같은 까닭이 있다.
"""

import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)

OK = {'status': 'ok'}
UNAVAILABLE = {'status': 'unavailable'}
# 빈칸 없이 쓴다. 다른 세 서버의 본문({"status":"ok"})과 글자까지 같게 한다.
# 프록시나 관리 도구가 본문을 글자 그대로 비교하도록 설정될 수 있다
COMPACT = {'separators': (',', ':')}


def status_response(body: dict, status: int = 200) -> JsonResponse:
    """상태 확인의 응답. 본문을 빈칸 없이 쓴다."""
    return JsonResponse(body, status=status, json_dumps_params=COMPACT)


def ping_database() -> None:
    """DB 에 SELECT 1 을 보낸다. 닿지 않으면 DatabaseError 를 낸다."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')


@require_safe
def health(request: HttpRequest) -> JsonResponse:
    """프로세스가 살아 있으면 200. DB 가 죽어도 200 이다. 다시 띄워도 낫지 않는 문제에 재시작을 되풀이하지 않는다."""
    return status_response(OK)


@require_safe
def ready(request: HttpRequest) -> JsonResponse:
    """DB 에 닿으면 200, 닿지 않으면 503."""
    try:
        ping_database()
    except DatabaseError as exc:
        # 예외의 글은 남기지 않는다. 접속 실패의 글에는 DB 주소와 계정 이름이 들어 있다
        logger.warning('DB 에 닿지 않는다: %s', type(exc).__name__)
        return status_response(UNAVAILABLE, status=503)
    return status_response(OK)
