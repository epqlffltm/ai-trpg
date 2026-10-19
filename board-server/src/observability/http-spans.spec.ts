// board-server/src/observability/http-spans.spec.ts

/**
 * 다른 서버를 부르는 fetch 의 client span(http-spans.ts)을 검증한다. 이 컴퓨터 안에 작은 서버를 띄워 부른다.
 */

import { createServer, IncomingHttpHeaders, Server } from 'node:http';
import { AddressInfo } from 'node:net';
import { SpanKind, SpanStatusCode } from '@opentelemetry/api';
import {
  parentIdOf,
  recordSpans,
  spanIdOf,
  traceIdOf,
} from '../../test/spans.js';
import { hostOf, methodOf, tracedFetch, UNREACHABLE } from './http-spans.js';
import { TRACEPARENT_HEADER } from './identifiers.js';
import { outgoingHeaders } from './request-context.js';
import { tracer } from './spans.js';

const recorder = recordSpans();

/** 띄운 서버. 받은 머리말을 모은다. */
interface Served {
  server: Server;
  url: string;
  received: IncomingHttpHeaders[];
}

/** 늘 status 로 답하는 서버를 띄운다. */
async function serve(status: number): Promise<Served> {
  const received: IncomingHttpHeaders[] = [];
  const server = createServer((request, response) => {
    received.push(request.headers);
    response.statusCode = status;
    response.end('{}');
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address() as AddressInfo;
  return {
    server,
    url: `http://127.0.0.1:${port}/api/v1/auth/jwks?kid=secret`,
    received,
  };
}

let served: Served | undefined;

afterEach(async () => {
  await new Promise(
    (resolve) => served?.server.close(resolve) ?? resolve(null),
  );
  served = undefined;
});

describe('hostOf, methodOf', () => {
  it('주소에서 호스트 이름만 꺼낸다', () => {
    expect(hostOf('http://auth-server:8000/api/v1/auth/jwks')).toBe(
      'auth-server',
    );
    expect(hostOf(new URL('https://example.com/x'))).toBe('example.com');
    expect(hostOf(new Request('http://notification-server:8004/a'))).toBe(
      'notification-server',
    );
    expect(hostOf('not a url')).toBe('');
  });

  it('메서드를 적지 않았으면 GET 이다', () => {
    expect(methodOf(undefined)).toBe('GET');
    expect(methodOf({ method: 'post' })).toBe('POST');
  });
});

describe('tracedFetch', () => {
  it('부모 span 이 없으면 span 없이 부르고 traceparent 를 건드리지 않는다', async () => {
    served = await serve(200);
    const traceparent = `00-${'a'.repeat(32)}-${'b'.repeat(16)}-00`;

    await tracedFetch(served.url, { headers: { traceparent } });

    expect(recorder.spans()).toEqual([]);
    expect(served.received[0][TRACEPARENT_HEADER]).toBe(traceparent);
  });

  it('부모 아래에 client span 을 걸고, 붙인 traceparent 를 그 span 으로 바꾼다', async () => {
    served = await serve(200);
    const url = served.url;

    await tracer().startActiveSpan('request', async (request) => {
      const response = await tracedFetch(url, { headers: outgoingHeaders() });
      expect(response.status).toBe(200);
      request.end();
    });

    const client = recorder.only('HTTP GET');
    expect(client.kind).toBe(SpanKind.CLIENT);
    expect(parentIdOf(client)).toBe(spanIdOf(recorder.only('request')));
    // 주소의 경로와 뒤의 값은 싣지 않는다
    expect(client.attributes).toEqual({
      'http.request.method': 'GET',
      'server.address': '127.0.0.1',
      'http.response.status_code': 200,
    });
    expect(served.received[0][TRACEPARENT_HEADER]).toBe(
      `00-${traceIdOf(client)}-${spanIdOf(client)}-01`,
    );
  });

  it('부르는 쪽이 traceparent 를 붙이지 않았으면 붙이지 않는다', async () => {
    served = await serve(204);
    const url = served.url;

    await tracer().startActiveSpan('request', async (request) => {
      await tracedFetch(url, { method: 'POST', body: '{}' });
      request.end();
    });

    expect(recorder.named('HTTP POST')).toHaveLength(1);
    expect(served.received[0][TRACEPARENT_HEADER]).toBeUndefined();
  });

  it('상대의 5xx 는 오류로 표시하고 4xx 는 표시하지 않는다', async () => {
    served = await serve(503);
    const url = served.url;

    await tracer().startActiveSpan('request', async (request) => {
      await tracedFetch(url);
      request.end();
    });

    expect(recorder.only('HTTP GET').status.code).toBe(SpanStatusCode.ERROR);
  });

  it('4xx 는 부른 쪽이 다룬다. 오류로 표시하지 않는다', async () => {
    served = await serve(404);
    const url = served.url;

    await tracer().startActiveSpan('request', async (request) => {
      await tracedFetch(url);
      request.end();
    });

    expect(recorder.only('HTTP GET').status.code).toBe(SpanStatusCode.UNSET);
  });

  it('닿지 못하면 오류로 표시하고 예외를 그대로 올린다. 예외의 글은 싣지 않는다', async () => {
    await tracer().startActiveSpan('request', async (request) => {
      await expect(tracedFetch('http://127.0.0.1:1/secret')).rejects.toThrow();
      request.end();
    });

    const client = recorder.only('HTTP GET');
    expect(client.status).toEqual({
      code: SpanStatusCode.ERROR,
      message: UNREACHABLE,
    });
    expect(client.events).toEqual([]);
  });
});
