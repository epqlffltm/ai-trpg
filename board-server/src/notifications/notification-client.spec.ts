// board-server/src/notifications/notification-client.spec.ts

/**
 * 알림 서버를 부르는 것(notification-client.ts)과 서명(signing.ts)을 검증한다.
 * 진짜 알림 서버는 띄우지 않는다. 이 프로세스 안에 작은 HTTP 서버를 띄워 받은 요청을 본다.
 */

import { createHmac } from 'node:crypto';
import { createServer, IncomingMessage, Server } from 'node:http';
import { AddressInfo } from 'node:net';
import {
  encode,
  HttpNotificationSender,
  PUT_PATH,
  resultOf,
  Sent,
  transportReason,
} from './notification-client.js';
import { recordSpans, spanIdOf, traceIdOf } from '../../test/spans.js';
import { tracer } from '../observability/spans.js';
import { OutgoingNotification } from './outgoing-notification.entity.js';
import { SIGNATURE_HEADER, sign, signedContent } from './signing.js';

const recorder = recordSpans();

const SECRET = 'board-notification-test-secret-of-32';
const SENT_AT = new Date('2026-10-19T03:00:00Z');

function sample(): OutgoingNotification {
  return Object.assign(new OutgoingNotification(), {
    id: '9',
    sourceKey: 'post.commented:7',
    userId: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
    kind: 'post.commented',
    payload: { board_slug: 'free', post_title: '첫 모험' },
  });
}

/** 받은 요청 하나. */
interface Received {
  path: string;
  signature: string;
  traceparent: string | undefined;
  body: string;
}

/** status 로 답하는 HTTP 서버를 띄운다. 받은 요청을 received 에 적는다. */
async function serve(
  status: number,
): Promise<{ server: Server; url: string; received: Received[] }> {
  const received: Received[] = [];
  const server = createServer((request: IncomingMessage, response) => {
    let body = '';
    request.on('data', (chunk: Buffer) => (body += chunk.toString('utf8')));
    request.on('end', () => {
      received.push({
        path: request.url ?? '',
        signature: String(request.headers[SIGNATURE_HEADER.toLowerCase()]),
        traceparent: request.headers.traceparent as string | undefined,
        body,
      });
      if (status === 302) {
        response.setHeader('Location', '/elsewhere');
      }
      response.writeHead(status).end();
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address() as AddressInfo;
  return { server, url: `http://127.0.0.1:${port}/`, received };
}

describe('sign', () => {
  it('결제 서버와 같은 모양으로 서명한다', () => {
    const expected = createHmac('sha256', SECRET)
      .update('1700000000.POST\n/x\n{}')
      .digest('hex');

    expect(signedContent(1700000000, 'POST', '/x', '{}')).toBe(
      '1700000000.POST\n/x\n{}',
    );
    expect(sign(SECRET, 1700000000, 'POST', '/x', '{}')).toBe(
      `t=1700000000,v1=${expected}`,
    );
  });
});

describe('encode', () => {
  it('알림 서버가 받는 네 칸만 싣는다', () => {
    expect(JSON.parse(encode(sample()))).toEqual({
      source_key: 'post.commented:7',
      user_id: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
      kind: 'post.commented',
      payload: { board_slug: 'free', post_title: '첫 모험' },
    });
  });
});

describe('resultOf', () => {
  it.each<[number, Sent]>([
    [201, { delivery: 'delivered' }],
    [200, { delivery: 'delivered' }],
    [401, { delivery: 'unavailable', reason: 'unauthorized' }],
    [408, { delivery: 'unavailable', reason: 'status_408' }],
    [429, { delivery: 'unavailable', reason: 'status_429' }],
    [500, { delivery: 'unavailable', reason: 'status_500' }],
    [503, { delivery: 'unavailable', reason: 'status_503' }],
    [409, { delivery: 'rejected', reason: 'status_409' }],
    [413, { delivery: 'rejected', reason: 'status_413' }],
    [422, { delivery: 'rejected', reason: 'status_422' }],
    [302, { delivery: 'rejected', reason: 'status_302' }],
  ])('%i 이면 %o 이다', (status, expected) => {
    expect(resultOf(status)).toEqual(expected);
  });
});

describe('transportReason', () => {
  it('시간이 다 된 것과 닿지 못한 것을 가른다', () => {
    const timeout = Object.assign(new Error('늦었다'), {
      name: 'TimeoutError',
    });

    expect(transportReason(timeout)).toBe('timeout');
    expect(transportReason(new TypeError('fetch failed'))).toBe('unreachable');
    expect(transportReason('글자')).toBe('unreachable');
  });
});

describe('HttpNotificationSender', () => {
  let server: Server | undefined;

  afterEach(async () => {
    await new Promise((resolve) => server?.close(resolve) ?? resolve(null));
    server = undefined;
  });

  it('알림 서버가 확인하는 그대로 서명해 보낸다', async () => {
    const served = await serve(201);
    server = served.server;
    const sender = new HttpNotificationSender(
      served.url,
      SECRET,
      () => SENT_AT,
    );

    const sent = await sender.send(sample());

    const [request] = served.received;
    expect(sent).toEqual({ delivery: 'delivered' });
    // 주소 끝의 / 는 떼고 붙인다. // 가 생기면 서명한 경로와 어긋난다
    expect(request.path).toBe(PUT_PATH);
    expect(request.body).toBe(encode(sample()));
    const sentAt = SENT_AT.getTime() / 1000;
    expect(request.signature).toBe(
      sign(SECRET, sentAt, 'POST', PUT_PATH, request.body),
    );
  });

  it('작업 밖에서 보내면 span 도 traceparent 도 없다', async () => {
    const served = await serve(201);
    server = served.server;

    await new HttpNotificationSender(served.url, SECRET).send(sample());

    expect(served.received[0].traceparent).toBeUndefined();
    expect(recorder.spans()).toEqual([]);
  });

  it('작업 안에서 보내면 client span 을 걸고 traceparent 로 추적을 잇는다. 서명은 그대로 맞는다', async () => {
    const served = await serve(201);
    server = served.server;
    const sender = new HttpNotificationSender(
      served.url,
      SECRET,
      () => SENT_AT,
    );

    await tracer().startActiveSpan('notification.send', async (job) => {
      await sender.send(sample());
      job.end();
    });

    const client = recorder.only('HTTP POST');
    const [request] = served.received;
    expect(request.traceparent).toBe(
      `00-${traceIdOf(client)}-${spanIdOf(client)}-01`,
    );
    expect(request.signature).toBe(
      sign(SECRET, SENT_AT.getTime() / 1000, 'POST', PUT_PATH, request.body),
    );
  });

  it('다른 주소로 가라는 답을 따라가지 않는다', async () => {
    const served = await serve(302);
    server = served.server;
    const sender = new HttpNotificationSender(served.url, SECRET);

    expect(await sender.send(sample())).toEqual({
      delivery: 'rejected',
      reason: 'status_302',
    });
    expect(served.received).toHaveLength(1);
  });

  it('닿지 못하면 다시 보낼 일이다', async () => {
    const sender = new HttpNotificationSender('http://127.0.0.1:1', SECRET);

    expect(await sender.send(sample())).toEqual({
      delivery: 'unavailable',
      reason: 'unreachable',
    });
  });
});
