// board-server/src/observability/request-logging.middleware.ts

/**
 * 요청마다 식별자를 정하고, 끝나면 한 줄을 남기는 미들웨어. 규격은 저장소 루트의 docs/observability.md 에 있다.
 *
 * 하는 일은 셋이다.
 *   1. 요청의 식별자(request_id)와 추적(trace_id)을 정해 건다. 밖에서 받은 값이 형식에 맞으면 이어 쓴다.
 *   2. 응답에 X-Request-ID 머리말로 식별자를 돌려준다. 문제를 알릴 때 이 값을 함께 알려 주면 그 요청의 기록을 찾는다.
 *   3. 응답이 다 나가면 한 줄을 남긴다. 무엇을(메서드, 경로의 틀), 어떻게(상태 코드, 걸린 시간) 처리했는지다.
 *
 * 처리하지 못한 예외는 예외 필터가 남긴다(errors/all-exceptions.filter.ts). 그 줄에도 여기서 건 식별자가 붙는다.
 *
 * 앱에 거는 규칙이라 setupApp 이 건다(app.setup.ts). 서버를 띄울 때와 테스트가 같은 것을 쓴다.
 * 문지기와 필터보다 먼저 돈다. 로그인하지 못한 요청(401)과 없는 주소(404)에도 식별자가 붙는다.
 *
 * 경로는 틀(/api/v1/board/posts/:id)로 적는다. 실제 주소에는 글 번호 같은 값이 들어 있어서,
 * 그대로 적으면 같은 API 가 주소마다 다른 것으로 세어진다. 맞는 틀이 없을 때(404)만 실제 경로를 따로 적는다.
 * 요청의 머리말과 본문, 주소 뒤에 붙는 값(?a=b)은 적지 않는다.
 */

import { Logger } from '@nestjs/common';
import {
  REQUEST_ID_HEADER,
  requestIdFrom,
  traceFrom,
  TRACEPARENT_HEADER,
} from './identifiers.js';
import { idsOf, RequestContext, runInRequest } from './request-context.js';

/** 요청 하나를 처리한 일의 이름 */
export const HTTP_OPERATION = 'http.request';
/** 맞는 경로의 틀이 없을 때(404) 틀 자리에 적는 표시 */
export const UNMATCHED_ROUTE = '(unmatched)';
/** 이 미들웨어가 남기는 로그의 이름 */
export const REQUEST_LOGGER = 'RequestLogging';

/** 서버의 잘못으로 보는 상태 코드의 시작 */
const SERVER_ERROR = 500;
/** 요청의 잘못으로 보는 상태 코드의 시작 */
const CLIENT_ERROR = 400;

/** 이 미들웨어가 읽는 요청의 부분. */
export interface IncomingRequest {
  method: string;
  /** 주소 뒤에 붙는 값(?a=b)을 뺀 경로 */
  path: string;
  headers: Record<string, string | string[] | undefined>;
  /** 라우터가 맞은 경로를 여기에 적어 둔다. 맞은 것이 없으면 비어 있다 */
  route?: { path?: unknown };
}

/** 이 미들웨어가 쓰는 응답의 부분. */
export interface OutgoingResponse {
  statusCode: number;
  setHeader(name: string, value: string): unknown;
  on(event: 'finish', listener: () => void): unknown;
}

/** 요청이 끝난 줄을 남기는 것. Nest 의 Logger 가 이 모양이다. 테스트가 줄을 모으는 것으로 바꿔 꽂는다 */
export interface RequestLog {
  log(message: object): void;
  error(message: object): void;
}

/** 상태 코드를 결과의 이름으로 바꾼다. 5xx 는 서버의 잘못, 4xx 는 요청의 잘못, 나머지는 성공이다. */
export function resultOf(statusCode: number): string {
  if (statusCode >= SERVER_ERROR) {
    return 'server_error';
  }
  return statusCode >= CLIENT_ERROR ? 'client_error' : 'success';
}

/**
 * 요청이 맞은 경로의 틀. 맞은 것이 없으면(404) 틀 자리에 표시를 적고 실제 경로를 따로 싣는다.
 *
 * 라우터는 요청을 처리하면서 맞은 경로를 요청에 적어 둔다. 그래서 응답이 나간 뒤에 읽는다.
 */
export function routeFields(request: IncomingRequest): Record<string, string> {
  const template = request.route?.path;
  if (typeof template === 'string') {
    return { route: template };
  }
  return { route: UNMATCHED_ROUTE, path: request.path };
}

/** 요청이 끝난 줄에 싣는 칸들. */
export function requestFields(
  request: IncomingRequest,
  statusCode: number,
  durationMs: number,
): Record<string, unknown> {
  return {
    message: '요청을 처리했다',
    operation: HTTP_OPERATION,
    method: request.method,
    ...routeFields(request),
    status_code: statusCode,
    duration_ms: durationMs,
    result: resultOf(statusCode),
  };
}

/**
 * 요청이 끝났다는 한 줄을 남긴다. 5xx 만 error 고 나머지는 info 다.
 *
 * 4xx 는 요청이 틀린 것이다. 서버는 제 일을 했다. warning 으로 올리면 로그인하지 않은 요청과 없는 주소가 경고를 메운다.
 * 식별자를 직접 싣는다. 이 줄은 응답이 다 나간 뒤에 남는다. 그때는 요청에 걸어 둔 값이 풀려 있을 수 있다.
 */
export function logFinished(
  log: RequestLog,
  context: RequestContext,
  fields: Record<string, unknown>,
  statusCode: number,
): void {
  const line = { ...fields, ...idsOf(context) };
  if (statusCode >= SERVER_ERROR) {
    log.error(line);
    return;
  }
  log.log(line);
}

/** 지금까지 걸린 시간(밀리초). started 는 performance.now() 의 값이다. */
function elapsedMs(started: number): number {
  return Math.round(performance.now() - started);
}

/**
 * 요청 식별 미들웨어를 만든다. log 는 요청이 끝난 줄을 남기는 것이다.
 */
export function requestLogging(
  log: RequestLog = new Logger(REQUEST_LOGGER),
): (
  request: IncomingRequest,
  response: OutgoingResponse,
  next: () => void,
) => void {
  return (request, response, next) => {
    const context: RequestContext = {
      requestId: requestIdFrom(
        request.headers[REQUEST_ID_HEADER.toLowerCase()],
      ),
      trace: traceFrom(request.headers[TRACEPARENT_HEADER]),
    };
    const started = performance.now();
    response.setHeader(REQUEST_ID_HEADER, context.requestId);
    response.on('finish', () => {
      const fields = requestFields(
        request,
        response.statusCode,
        elapsedMs(started),
      );
      logFinished(log, context, fields, response.statusCode);
    });
    runInRequest(context, next);
  };
}
