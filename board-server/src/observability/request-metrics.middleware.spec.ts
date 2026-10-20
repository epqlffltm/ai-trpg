// board-server/src/observability/request-metrics.middleware.spec.ts

/**
 * 요청마다 HTTP 메트릭 셋을 세는 미들웨어(request-metrics.middleware.ts)를 검증한다. 가짜 요청과 응답으로 돌린다.
 * 앱을 거친 것(경로의 틀, 404)은 test/metrics.e2e-spec.ts 가 본다.
 */

import { recordMetrics } from '../../test/metrics.js';
import { IncomingRequest } from './request-logging.middleware.js';
import { requestMetrics } from './request-metrics.middleware.js';

const metrics = recordMetrics();

/** 가짜 요청. 경로의 틀이 정해진 것이다(라우터를 지났다). */
function makeRequest(): IncomingRequest {
  return {
    method: 'POST',
    path: '/api/v1/board/posts/7/reports',
    headers: {},
    route: { path: '/api/v1/board/posts/:id/reports' },
  };
}

/** 가짜 응답. close() 로 "응답이 닫혔다"를 알린다. */
function makeResponse(statusCode = 201) {
  let listener: (() => void) | undefined;
  return {
    statusCode,
    once: (_event: 'close', next: () => void) => {
      listener = next;
    },
    close: () => listener?.(),
  };
}

describe('requestMetrics', () => {
  it('응답이 닫힐 때 끝난 요청으로 세고 처리 중인 수에서 뺀다', async () => {
    const response = makeResponse();
    let nextCalled = false;

    requestMetrics()(makeRequest(), response, () => {
      nextCalled = true;
    });
    const whileOpen = await metrics.current.value(
      'http_server_active_requests',
    );
    response.close();

    expect(nextCalled).toBe(true);
    expect(whileOpen).toBe(1);
    expect(await metrics.current.value('http_server_active_requests')).toBe(0);
    expect(
      await metrics.current.value('http_server_requests', {
        method: 'POST',
        route: '/api/v1/board/posts/:id/reports',
        status_code: 201,
      }),
    ).toBe(1);
    expect(
      await metrics.current.value('http_server_request_duration', {
        method: 'POST',
        route: '/api/v1/board/posts/:id/reports',
      }),
    ).toBe(1);
  });

  it('닫히기 전에는 끝난 요청으로 세지 않는다', async () => {
    requestMetrics()(makeRequest(), makeResponse(), () => undefined);

    expect(await metrics.current.points('http_server_requests')).toEqual([]);
  });
});
