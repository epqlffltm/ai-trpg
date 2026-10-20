// board-server/src/observability/request-metrics.middleware.ts

/**
 * 요청마다 HTTP 메트릭 셋을 세는 express 미들웨어. 맨 앞에 건다(app.setup.ts). 결제 서버의 measureRequests 와 같다.
 *
 *   - http_server_requests_total: 끝난 요청의 수. method, route(경로의 틀), status_code
 *   - http_server_request_duration_seconds: 요청을 받아 응답을 끝낼 때까지. method, route
 *   - http_server_active_requests: 지금 처리 중인 요청의 수
 *
 * route 는 로그의 route 와 같은 값이다(request-logging.middleware.ts 의 routeFields). 맞은 것이 없으면(404) (unmatched) 다.
 * 상태 확인(/health, /health/ready)도 센다. 다른 서버와 같다. 스택의 확인이 이 요청 수로 메트릭이 오는지 본다.
 * 응답이 닫힐 때(close) 센다. 받는 쪽이 중간에 끊어도 센다. 그때의 상태 코드는 그때까지 정해진 것이다.
 */

import { UpDownCounter } from '@opentelemetry/api';
import { IncomingRequest, routeFields } from './request-logging.middleware.js';
import { ClosingResponse } from './request-spans.middleware.js';
import { instruments, recordRequest, secondsSince } from './metrics.js';

/** 끝난 요청 하나를 센다. 처리 중인 수(active)에서 뺀다. 시작할 때 더한 그 계측기다. */
export function finishRequest(
  active: UpDownCounter,
  request: IncomingRequest,
  statusCode: number,
  started: number,
): void {
  active.add(-1);
  recordRequest(
    request.method,
    routeFields(request).route,
    statusCode,
    secondsSince(started),
  );
}

/** 요청마다 HTTP 메트릭을 세는 미들웨어. 보낼 곳이 없으면(noop) 세기만 하고 아무것도 나가지 않는다. */
export function requestMetrics(): (
  request: IncomingRequest,
  response: ClosingResponse,
  next: () => void,
) => void {
  return (request, response, next) => {
    const started = performance.now();
    const active = instruments().httpActiveRequests;
    active.add(1);
    response.once('close', () =>
      finishRequest(active, request, response.statusCode, started),
    );
    next();
  };
}
