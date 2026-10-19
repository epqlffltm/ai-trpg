// board-server/src/observability/request-spans.middleware.ts

/**
 * 요청마다 서버 span 을 거는 미들웨어. 앱의 맨 앞에 건다(app.setup.ts). 안의 로그와 쿼리가 이 span 아래에 놓인다.
 *
 * 이름은 메서드와 경로의 틀이다(GET /api/v1/board/posts/:id). 실제 주소가 아니다. 맞은 것이 없으면(404) (unmatched) 다.
 * 틀은 라우터가 요청을 처리한 뒤에 알 수 있다(request.route). 그래서 메서드만으로 시작하고 끝날 때 이름을 고친다.
 *
 * 받은 traceparent 가 형식에 맞으면 그 아래에 붙는다(부른 서버의 span 이 부모가 된다). 받는 규칙은 로그와 같다.
 * 상태 확인(/health, /health/ready)은 span 을 걸지 않는다. 10초마다 오는 확인이 추적을 메우지 않게 한다.
 * span 에는 메서드, 경로의 틀, 상태 코드, 요청 식별자만 싣는다. 머리말, 주소 뒤의 값, 본문, 예외의 글은 싣지 않는다.
 *
 * 처리하지 못한 예외는 예외 필터가 500 응답으로 바꾼다. 여기까지 예외로 올라오지 않는다. 응답의 상태 코드로 본다.
 * span 은 응답이 끝나거나 연결이 끊길 때(close) 끝난다.
 */

import {
  context,
  Span,
  SpanKind,
  SpanStatusCode,
  trace,
} from '@opentelemetry/api';
import { TRACEPARENT_HEADER } from './identifiers.js';
import {
  IncomingRequest,
  PROBE_ROUTES,
  routeFields,
} from './request-logging.middleware.js';
import { remoteParent, tracer } from './spans.js';

/** 서버의 잘못으로 보는 상태 코드의 시작 */
const SERVER_ERROR = 500;

/** 이 미들웨어가 쓰는 응답의 부분. */
export interface ClosingResponse {
  statusCode: number;
  once(event: 'close', listener: () => void): unknown;
}

/** 끝난 요청을 span 에 적고 끝낸다. 이름을 경로의 틀로 고친다. 서버의 잘못(5xx)만 오류로 표시한다. */
export function finishServerSpan(
  span: Span,
  request: IncomingRequest,
  statusCode: number,
): void {
  const route = routeFields(request).route;
  span.updateName(`${request.method} ${route}`);
  span.setAttribute('http.route', route);
  span.setAttribute('http.response.status_code', statusCode);
  if (statusCode >= SERVER_ERROR) {
    span.setStatus({ code: SpanStatusCode.ERROR });
  }
  span.end();
}

/** 요청마다 서버 span 을 거는 미들웨어를 만든다. 보낼 곳이 없으면(noop) 아무것도 남지 않는다. */
export function requestSpans(): (
  request: IncomingRequest,
  response: ClosingResponse,
  next: () => void,
) => void {
  return (request, response, next) => {
    if (PROBE_ROUTES.has(request.path)) {
      next();
      return;
    }
    const span = tracer().startSpan(
      request.method,
      {
        kind: SpanKind.SERVER,
        attributes: { 'http.request.method': request.method },
      },
      remoteParent(request.headers[TRACEPARENT_HEADER]),
    );
    response.once('close', () =>
      finishServerSpan(span, request, response.statusCode),
    );
    context.with(trace.setSpan(context.active(), span), next);
  };
}
