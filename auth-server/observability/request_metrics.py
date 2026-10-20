# auth-server/observability/request_metrics.py

"""
요청마다 HTTP 메트릭 셋을 세는 미들웨어. 설정의 MIDDLEWARE 맨 앞에 둔다(span 을 거는 것보다 앞).

  - http_server_requests_total: 끝난 요청의 수. method, route(경로의 틀), status_code
  - http_server_request_duration_seconds: 요청을 받아 응답을 끝낼 때까지. method, route
  - http_server_active_requests: 지금 처리 중인 요청의 수. 워커(프로세스)마다다

route 는 로그의 route 와 같은 값이다. 맞은 것이 없으면(404) (unmatched) 다. 실제 주소는 label 이 아니다.
상태 확인(/health, /health/ready)도 센다. 다른 서버와 같다. 스택의 확인이 이 요청 수로 메트릭이 오는지 본다.
뷰에서 난 예외는 Django 가 500 응답으로 바꾼다. 미들웨어에서 예외가 올라오면 500 으로 세고 그대로 올린다.
"""

import time
from http import HTTPStatus

from observability.metrics import instruments, record_request
from observability.middleware import route_fields


class RequestMetricsMiddleware:
    """요청마다 HTTP 메트릭을 센다. 보낼 곳이 없으면(NoOp) 세기만 하고 아무것도 나가지 않는다."""

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        active = instruments().http_active_requests
        active.add(1)
        started = time.perf_counter()
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        try:
            response = self.get_response(request)
            status_code = response.status_code
            return response
        finally:
            active.add(-1)
            record_request(request.method, route_fields(request)['route'], status_code, time.perf_counter() - started)
