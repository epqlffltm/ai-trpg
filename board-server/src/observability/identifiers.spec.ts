// board-server/src/observability/identifiers.spec.ts

/**
 * 요청을 가리키는 식별자의 규칙(identifiers.ts)과 그것을 들고 있는 곳(request-context.ts)을 검증한다.
 */

import {
  acceptRequestId,
  formatTraceparent,
  newTrace,
  parseTraceparent,
  requestIdFrom,
  traceFrom,
} from './identifiers.js';
import {
  currentIds,
  outgoingHeaders,
  runInRequest,
} from './request-context.js';

const TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736';
const TRACEPARENT = `00-${TRACE_ID}-00f067aa0ba902b7-01`;
const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('requestIdFrom', () => {
  it.each([
    '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
    'req_12345678',
    'A1b2.C3d4-E5f6',
    'a'.repeat(8),
    'a'.repeat(64),
  ])('형식에 맞는 식별자(%j)는 그대로 쓴다', (value) => {
    expect(acceptRequestId(value)).toBe(value);
    expect(requestIdFrom(value)).toBe(value);
  });

  it.each([
    undefined,
    null,
    '',
    'short',
    'a'.repeat(65),
    'a'.repeat(5000),
    'has space in it',
    'line\nbreak-12345',
    'carriage\rreturn-1',
    'tab\tinside-12345',
    'null\u0000byte-12345',
    'escape\u001b[31m-12345',
    '한글로-된-식별자-12345',
    '{"injected":"json"}',
    'semi;colon-12345',
    'slash/inside-12345',
    // 같은 머리말이 여러 번 오면 배열로 온다
    ['request-12345', 'request-67890'],
    12345678,
  ])('형식에 맞지 않는 값(%j)은 새 UUID 로 바꾼다', (value) => {
    expect(acceptRequestId(value)).toBeUndefined();

    const replaced = requestIdFrom(value);

    // 고쳐 쓰지 않고 새로 만든다. 받은 값의 어느 부분도 남지 않는다
    expect(replaced).toMatch(UUID);
    expect(replaced).not.toBe(value);
  });

  it('새로 만드는 식별자는 매번 다르다', () => {
    expect(requestIdFrom(undefined)).not.toBe(requestIdFrom(undefined));
  });
});

describe('traceFrom', () => {
  it('traceparent 의 추적을 이어 간다', () => {
    const trace = parseTraceparent(TRACEPARENT);

    expect(trace).toEqual({ traceId: TRACE_ID, flags: '01' });
    expect(traceFrom(TRACEPARENT)).toEqual(trace);
  });

  it.each([
    undefined,
    '',
    'garbage',
    TRACE_ID,
    // 모르는 버전
    `01-${TRACE_ID}-00f067aa0ba902b7-01`,
    `ff-${TRACE_ID}-00f067aa0ba902b7-01`,
    // 대문자
    `00-${TRACE_ID.toUpperCase()}-00f067aa0ba902b7-01`,
    // 길이가 틀리다
    `00-${TRACE_ID.slice(0, -1)}-00f067aa0ba902b7-01`,
    `00-${TRACE_ID}-00f067aa0ba902-01`,
    // 0 으로만 된 식별자
    `00-${'0'.repeat(32)}-00f067aa0ba902b7-01`,
    `00-${TRACE_ID}-${'0'.repeat(16)}-01`,
    // 줄바꿈으로 다른 값을 끼워 넣으려는 것
    `${TRACEPARENT}\nX-Injected: 1`,
    TRACEPARENT + 'x'.repeat(500),
    [TRACEPARENT],
  ])('형식에 맞지 않는 traceparent(%j)면 새 추적을 시작한다', (value) => {
    expect(parseTraceparent(value)).toBeUndefined();

    const trace = traceFrom(value);

    expect(trace.traceId).toMatch(/^[0-9a-f]{32}$/);
    expect(trace.traceId).not.toBe(TRACE_ID);
  });

  it('다른 서버에 보낼 때 추적은 그대로 두고 부모 식별자는 새로 만든다', () => {
    const trace = { traceId: TRACE_ID, flags: '01' };

    const first = formatTraceparent(trace);
    const second = formatTraceparent(trace);

    expect(first).toMatch(new RegExp(`^00-${TRACE_ID}-[0-9a-f]{16}-01$`));
    // 받는 쪽이 다시 읽을 수 있는 모양이다
    expect(parseTraceparent(first)).toEqual(trace);
    expect(first).not.toBe(second);
  });
});

describe('runInRequest', () => {
  it('식별자는 요청 안에서만 걸려 있다', () => {
    const trace = newTrace();

    expect(currentIds()).toEqual({});
    runInRequest({ requestId: 'request-12345', trace }, () => {
      expect(currentIds()).toEqual({
        request_id: 'request-12345',
        trace_id: trace.traceId,
      });
      expect(parseTraceparent(outgoingHeaders().traceparent)).toEqual(trace);
    });
    expect(currentIds()).toEqual({});
    expect(outgoingHeaders()).toEqual({});
  });

  it('기다렸다 이어지는 일에도 식별자가 따라간다', async () => {
    const trace = newTrace();

    const ids = await runInRequest(
      { requestId: 'request-12345', trace },
      async () => {
        await new Promise((resolve) => setTimeout(resolve, 1));
        return currentIds();
      },
    );

    expect(ids.request_id).toBe('request-12345');
  });

  it('동시에 처리되는 요청끼리 섞이지 않는다', async () => {
    const handle = (requestId: string) =>
      runInRequest({ requestId, trace: newTrace() }, async () => {
        // 다른 요청이 끼어들 틈을 준다
        await new Promise((resolve) => setTimeout(resolve, 1));
        return currentIds();
      });

    const [first, second] = await Promise.all([
      handle('request-aaaa'),
      handle('request-bbbb'),
    ]);

    expect(first.request_id).toBe('request-aaaa');
    expect(second.request_id).toBe('request-bbbb');
    expect(first.trace_id).not.toBe(second.trace_id);
  });
});
