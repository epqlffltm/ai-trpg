# notification-server/app/observability/request_metrics.py

"""
요청마다 HTTP 메트릭 셋을 세는 미들웨어. 미들웨어의 맨 바깥에 둔다(app/main.py). 결제 서버의 measureRequests 와 같다.

  - http_server_requests_total: 끝난 요청의 수. method, route(경로의 틀), status_code
  - http_server_request_duration_seconds: 요청을 받아 응답을 끝낼 때까지. method, route
  - http_server_active_requests: 지금 처리 중인 요청의 수

route 는 로그의 route 와 같은 값이다. 맞은 것이 없으면(404) (unmatched) 다. 실제 주소는 label 이 아니다.
상태 확인(/health, /health/ready)도 센다. 결제 서버와 같다. 스택의 확인이 이 요청 수로 메트릭이 오는지 본다.
응답을 시작하기 전에 예외가 나면 500 으로 센다(예외 처리기가 500 을 돌려준다).
"""

import time
from http import HTTPStatus

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.metrics import instruments, record_request
from app.observability.middleware import route_fields


class RequestMetricsMiddleware:
    """요청마다 HTTP 메트릭을 센다. 보낼 곳이 없으면(NoOp) 세기만 하고 아무것도 나가지 않는다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        # 응답이 시작될 때의 상태 코드. 응답이 시작되기 전에 예외가 나면 비어 있다
        seen: dict[str, int] = {}

        async def send_watching(message: Message) -> None:
            if message['type'] == 'http.response.start':
                seen['status_code'] = message['status']
            await send(message)

        active = instruments().http_active_requests
        active.add(1)
        started = time.perf_counter()
        try:
            await self.app(scope, receive, send_watching)
        finally:
            active.add(-1)
            status_code = seen.get('status_code', HTTPStatus.INTERNAL_SERVER_ERROR)
            record_request(
                str(scope.get('method', '')), route_fields(scope)['route'], status_code, time.perf_counter() - started
            )
