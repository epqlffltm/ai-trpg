// board-server/src/observability/request-logging.middleware.spec.ts

/**
 * 요청 식별 미들웨어(request-logging.middleware.ts)를 검증한다. 서버를 띄우지 않고 가짜 요청과 응답을 넣는다.
 * 앱에 실제로 걸려 있는지는 test/observability.e2e-spec.ts 가 본다.
 */

import { currentIds } from './request-context.js';
import {
  IncomingRequest,
  levelOf,
  requestLogging,
  resultOf,
  routeFields,
} from './request-logging.middleware.js';

const TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736';
const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** 줄을 모으는 가짜 로그. */
function makeLog() {
  const lines: { level: string; fields: Record<string, unknown> }[] = [];
  return {
    lines,
    debug: (fields: object) =>
      lines.push({ level: 'debug', fields: fields as Record<string, unknown> }),
    log: (fields: object) =>
      lines.push({ level: 'info', fields: fields as Record<string, unknown> }),
    warn: (fields: object) =>
      lines.push({ level: 'warn', fields: fields as Record<string, unknown> }),
    error: (fields: object) =>
      lines.push({ level: 'error', fields: fields as Record<string, unknown> }),
  };
}

/** 가짜 요청. */
function makeRequest(
  overrides: Partial<IncomingRequest> = {},
): IncomingRequest {
  return { method: 'GET', path: '/health', headers: {}, ...overrides };
}

/** 가짜 응답. 붙은 머리말을 기억하고, finish() 로 "응답이 다 나갔다"를 알린다. */
function makeResponse(statusCode = 200) {
  const headers = new Map<string, string>();
  const listeners: (() => void)[] = [];
  return {
    statusCode,
    headers,
    setHeader: (name: string, value: string) => headers.set(name, value),
    on: (_event: 'finish', listener: () => void) => listeners.push(listener),
    finish: () => listeners.forEach((listener) => listener()),
  };
}

describe('requestLogging', () => {
  it('식별자가 없는 요청에 새 식별자를 주고 응답에 돌려준다', () => {
    const response = makeResponse();

    requestLogging(makeLog())(makeRequest(), response, () => undefined);

    expect(response.headers.get('X-Request-ID')).toMatch(UUID);
  });

  it('형식에 맞는 식별자는 그대로 쓴다', () => {
    const response = makeResponse();
    const request = makeRequest({
      headers: { 'x-request-id': 'client-chosen-id-0001' },
    });

    requestLogging(makeLog())(request, response, () => undefined);

    expect(response.headers.get('X-Request-ID')).toBe('client-chosen-id-0001');
  });

  it.each([
    'short',
    'a'.repeat(65),
    'request-12345\r\n{"level":"error","message":"forged"}',
    'has space in it',
  ])('형식에 맞지 않는 식별자(%j)는 새것으로 바꾼다', (value) => {
    const log = makeLog();
    const response = makeResponse();
    const request = makeRequest({ headers: { 'x-request-id': value } });

    requestLogging(log)(request, response, () => undefined);
    response.finish();

    expect(response.headers.get('X-Request-ID')).toMatch(UUID);
    // 받은 값은 응답에도 로그에도 남지 않는다
    expect(JSON.stringify(log.lines)).not.toContain('forged');
    expect(log.lines[0].fields.request_id).toBe(
      response.headers.get('X-Request-ID'),
    );
  });

  it('다음 처리기는 식별자가 걸린 채로 돈다', () => {
    let seen = {};
    const request = makeRequest({
      headers: {
        'x-request-id': 'client-chosen-id-0001',
        traceparent: `00-${TRACE_ID}-00f067aa0ba902b7-01`,
      },
    });

    requestLogging(makeLog())(request, makeResponse(), () => {
      seen = currentIds();
    });

    expect(seen).toEqual({
      request_id: 'client-chosen-id-0001',
      trace_id: TRACE_ID,
    });
  });

  it('응답이 다 나가면 한 줄을 남긴다', () => {
    const log = makeLog();
    const response = makeResponse(200);
    const request = makeRequest({
      method: 'GET',
      path: '/api/v1/board/posts/1234',
      route: { path: '/api/v1/board/posts/:id' },
    });

    requestLogging(log)(request, response, () => undefined);
    expect(log.lines).toEqual([]);
    response.finish();

    const [line] = log.lines;
    expect(line.level).toBe('info');
    expect(line.fields).toMatchObject({
      message: '요청을 처리했다',
      operation: 'http.request',
      method: 'GET',
      route: '/api/v1/board/posts/:id',
      status_code: 200,
      result: 'success',
      request_id: response.headers.get('X-Request-ID'),
    });
    expect(line.fields.trace_id).toMatch(/^[0-9a-f]{32}$/);
    expect(Number.isInteger(line.fields.duration_ms)).toBe(true);
    // 실제 주소는 남기지 않는다. 글 번호가 들어 있다
    expect(JSON.stringify(line)).not.toContain('1234');
  });

  it.each([
    [200, 'info', 'success'],
    [204, 'info', 'success'],
    [304, 'info', 'success'],
    [400, 'info', 'client_error'],
    [401, 'info', 'client_error'],
    [404, 'info', 'client_error'],
    [409, 'info', 'client_error'],
    [500, 'error', 'server_error'],
    [503, 'error', 'server_error'],
  ])('상태 코드 %i 는 %s 수준, 결과는 %s 다', (statusCode, level, result) => {
    const log = makeLog();
    const response = makeResponse(statusCode);

    requestLogging(log)(makeRequest(), response, () => undefined);
    response.finish();

    expect(log.lines[0].level).toBe(level);
    expect(log.lines[0].fields.result).toBe(result);
    expect(resultOf(statusCode)).toBe(result);
  });

  it('머리말과 주소 뒤에 붙은 값은 남기지 않는다', () => {
    const log = makeLog();
    const response = makeResponse(401);
    const request = makeRequest({
      path: '/api/v1/board/me',
      route: { path: '/api/v1/board/me' },
      headers: {
        authorization: 'Bearer some-secret-token-value',
        cookie: 'refresh_token=cookie-secret-value',
      },
    });

    requestLogging(log)(request, response, () => undefined);
    response.finish();

    const text = JSON.stringify(log.lines);
    expect(text).not.toContain('some-secret-token-value');
    expect(text).not.toContain('cookie-secret-value');
  });
});

describe('상태 확인 요청의 수준', () => {
  it.each([
    ['/health', 200, 'debug'],
    ['/health/ready', 200, 'debug'],
    ['/health/ready', 404, 'debug'],
    // 준비 안 됨은 이 주소의 답이다. 서버의 잘못(error)이 아니다
    ['/health/ready', 503, 'warn'],
    // 처리하지 못한 예외는 다른 주소처럼 error 다
    ['/health/ready', 500, 'error'],
  ])('%s 의 %i 는 %s 다', (route, statusCode, level) => {
    expect(levelOf(route, statusCode)).toBe(level);
  });

  it('다른 주소는 수준이 그대로다', () => {
    expect(levelOf('/api/v1/board/me', 503)).toBe('error');
    expect(levelOf('/api/v1/board/me', 200)).toBe('log');
    expect(levelOf(undefined, 200)).toBe('log');
  });

  it('상태 확인의 성공은 debug 로 남긴다', () => {
    const log = makeLog();
    const response = makeResponse(200);
    const request = makeRequest({ route: { path: '/health' } });

    requestLogging(log)(request, response, () => undefined);
    response.finish();

    expect(log.lines.map((line) => line.level)).toEqual(['debug']);
  });
});

describe('routeFields', () => {
  it('맞은 경로의 틀을 적는다', () => {
    const request = makeRequest({
      path: '/api/v1/board/posts/1234',
      route: { path: '/api/v1/board/posts/:id' },
    });

    expect(routeFields(request)).toEqual({ route: '/api/v1/board/posts/:id' });
  });

  it('맞은 틀이 없으면 틀 자리에 표시를 적고 실제 경로를 따로 싣는다', () => {
    const request = makeRequest({ path: '/no/such/address' });

    expect(routeFields(request)).toEqual({
      route: '(unmatched)',
      path: '/no/such/address',
    });
  });

  it('Nest 의 404 틀(*path)에 맞은 것도 맞은 틀이 없는 것이다', () => {
    const request = makeRequest({
      path: '/no/such',
      originalUrl: '/api/v1/board/no/such?x=secret',
      route: { path: '*path' },
    });

    expect(routeFields(request)).toEqual({
      route: '(unmatched)',
      path: '/api/v1/board/no/such',
    });
  });
});
