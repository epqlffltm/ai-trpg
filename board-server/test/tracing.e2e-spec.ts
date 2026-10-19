// board-server/test/tracing.e2e-spec.ts

/**
 * 앱을 통째로 만들어 span 을 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다. 남긴 span 은 메모리에 모은다(test/spans.ts).
 * 규격은 저장소 루트의 docs/observability.md 의 "3. 추적"에 있다.
 *
 * 보는 것.
 *   - 요청: 이름(메서드와 경로의 틀), 받은 traceparent 의 아래, 요청 식별자, 상태 코드, 5xx 의 오류 표시, 로그의 trace_id
 *   - 상태 확인과 없는 주소
 *   - 쿼리: 요청과 작업 아래에 놓이고, 문장과 값은 싣지 않는다
 *   - 보내는 작업: 작업의 span 아래에 쿼리와 알림 서버를 부른 span, 알림 서버에 간 traceparent, 할 일이 없던 바퀴
 */

import { createServer, IncomingHttpHeaders, Server } from 'node:http';
import { AddressInfo } from 'node:net';
import { Controller, Get, Module } from '@nestjs/common';
import { NestExpressApplication } from '@nestjs/platform-express';
import { SpanKind, SpanStatusCode } from '@opentelemetry/api';
import { ReadableSpan } from '@opentelemetry/sdk-trace';
import request from 'supertest';
import { DataSource } from 'typeorm';
import { API_PREFIX } from '../src/app.setup.js';
import { Public } from '../src/auth/public.decorator.js';
import { HttpNotificationSender } from '../src/notifications/notification-client.js';
import { NOTIFICATION_SENDER } from '../src/notifications/notification-dispatcher.js';
import { NotificationDispatchRunner } from '../src/notifications/notification-dispatcher.runner.js';
import { OutgoingNotification } from '../src/notifications/outgoing-notification.entity.js';
import { JsonLogger } from '../src/observability/json-logger.js';
import { tracer } from '../src/observability/spans.js';
import { both, createTestApp, Customize } from './app.js';
import { clearData } from './data.js';
import { parentIdOf, recordSpans, spanIdOf, traceIdOf } from './spans.js';

const API = `/${API_PREFIX}`;
const TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736';
const PARENT_ID = '00f067aa0ba902b7';
const SECRET = 'board-notification-test-secret-of-32';
// 쿼리의 값으로 넘겨 span 에 실리지 않는지 볼 글자
const SECRET_IN_QUERY = 'secret-search-term';

/** 처리하지 못한 예외를 내는 컨트롤러. */
@Public()
@Controller('broken')
class BrokenController {
  @Get(':id')
  read(): never {
    throw new RangeError('부서졌다');
  }
}

@Module({ controllers: [BrokenController] })
class ProbeModule {}

/** 받은 머리말을 모으는 알림 서버. 늘 201 이다. */
class FakeNotificationServer {
  readonly received: IncomingHttpHeaders[] = [];
  private server: Server | undefined;

  /** 띄우고 주소를 돌려준다. */
  async start(): Promise<string> {
    this.server = createServer((incoming, response) => {
      this.received.push(incoming.headers);
      incoming.resume();
      incoming.on('end', () => response.writeHead(201).end());
    });
    await new Promise<void>((resolve) =>
      this.server?.listen(0, '127.0.0.1', resolve),
    );
    const { port } = this.server.address() as AddressInfo;
    return `http://127.0.0.1:${port}`;
  }

  /** 끈다. */
  stop(): Promise<void> {
    return new Promise((resolve) => this.server?.close(() => resolve()));
  }
}

const recorder = recordSpans();
const notifications = new FakeNotificationServer();
let app: NestExpressApplication;
let lines: string[];

/** 알림 서버를 부르는 것을 가짜 알림 서버로 바꿔 꽂는다. */
function useNotificationServer(url: string): Customize {
  return (builder) =>
    builder
      .overrideProvider(NOTIFICATION_SENDER)
      .useValue(new HttpNotificationSender(url, SECRET));
}

beforeAll(async () => {
  const url = await notifications.start();
  app = await createTestApp(both(useNotificationServer(url)), [ProbeModule]);
  // 타이머의 바퀴가 테스트가 부르는 바퀴와 겹치지 않게 멈춘다
  app.get(NotificationDispatchRunner).onModuleDestroy();
  app.useLogger(
    new JsonLogger(
      { service: 'board-server', environment: 'test', version: 'test' },
      'info',
      (line) => lines.push(line),
    ),
  );
});

afterAll(async () => {
  app.useLogger(['warn', 'error', 'fatal']);
  await app.close();
  await notifications.stop();
});

beforeEach(async () => {
  await clearData(app);
  recorder.clear();
  lines = [];
});

/** 요청의 span(server) 하나. 하나가 아니면 실패한다. */
function serverSpan(): ReadableSpan {
  const found = recorder
    .spans()
    .filter((span) => span.kind === SpanKind.SERVER);
  expect(found).toHaveLength(1);
  return found[0];
}

/** 요청이 끝난 줄. */
function finishedLine(): Record<string, unknown> {
  const finished = lines
    .map((line) => JSON.parse(line) as Record<string, unknown>)
    .filter((entry) => 'status_code' in entry);
  expect(finished).toHaveLength(1);
  return finished[0];
}

/** 요청의 span 이 끝나기를(응답이 닫히기를) 기다린다. */
async function settled(): Promise<void> {
  await new Promise((resolve) => setImmediate(resolve));
}

describe('요청의 span', () => {
  it('경로의 틀로 이름을 짓고, 받은 traceparent 아래에 놓인다(flags 00 이어도 남긴다)', async () => {
    const response = await request(app.getHttpServer())
      .get(`${API}/boards`)
      .set('traceparent', `00-${TRACE_ID}-${PARENT_ID}-00`);
    await settled();

    const span = serverSpan();
    expect(span.name).toBe(`GET ${API}/boards`);
    expect(traceIdOf(span)).toBe(TRACE_ID);
    expect(parentIdOf(span)).toBe(PARENT_ID);
    expect(span.attributes).toEqual({
      'http.request.method': 'GET',
      'http.route': `${API}/boards`,
      'http.response.status_code': 200,
      request_id: response.headers['x-request-id'],
    });
    expect(span.status.code).toBe(SpanStatusCode.UNSET);
  });

  it('그 요청의 로그 줄의 trace_id 가 span 의 것이다', async () => {
    await request(app.getHttpServer()).get(`${API}/boards`);
    await settled();

    expect(finishedLine().trace_id).toBe(traceIdOf(serverSpan()));
  });

  it('요청 안의 쿼리는 그 아래에 놓인다. 문장과 값은 싣지 않는다', async () => {
    await request(app.getHttpServer())
      .get(`${API}/posts`)
      .query({ q: SECRET_IN_QUERY });
    await settled();

    const parent = spanIdOf(serverSpan());
    const queries = recorder
      .spans()
      .filter((span) => span.name.startsWith('db '));
    expect(queries.length).toBeGreaterThan(0);
    for (const query of queries) {
      expect(parentIdOf(query)).toBe(parent);
      expect(query.attributes['db.system.name']).toBe('postgresql');
    }
    expect(queries.map((query) => query.name)).toContain('db SELECT posts');
    expect(
      JSON.stringify(recorder.spans().map((span) => span.attributes)),
    ).not.toContain(SECRET_IN_QUERY);
  });

  it('상태 확인은 span 을 걸지 않는다. 그 안의 쿼리도 남지 않는다', async () => {
    await request(app.getHttpServer()).get('/health/ready').expect(200);
    await request(app.getHttpServer()).get('/health').expect(200);
    await settled();

    expect(recorder.spans()).toEqual([]);
  });

  it('없는 주소는 (unmatched) 다. 실제 경로는 싣지 않는다', async () => {
    await request(app.getHttpServer()).get(`${API}/nowhere/secret-path`);
    await settled();

    const span = serverSpan();
    expect(span.name).toBe('GET (unmatched)');
    expect(JSON.stringify(span.attributes)).not.toContain('secret-path');
  });

  it('처리하지 못한 예외(500)는 오류로 표시한다. 예외의 글은 싣지 않는다', async () => {
    lines = [];
    await request(app.getHttpServer()).get(`${API}/broken/1`).expect(500);
    await settled();

    const span = serverSpan();
    expect(span.name).toBe(`GET ${API}/broken/:id`);
    expect(span.status.code).toBe(SpanStatusCode.ERROR);
    expect(span.events).toEqual([]);
  });
});

describe('쿼리의 span', () => {
  it('DB 가 거절한 쿼리는 SQLSTATE 만 적는다', async () => {
    const dataSource = app.get(DataSource);

    await tracer().startActiveSpan('job', async (job) => {
      await expect(
        dataSource.query(`SELECT 'secret-value' FROM "no_such_table"`),
      ).rejects.toThrow();
      job.end();
    });

    const query = recorder.only('db SELECT no_such_table');
    expect(query.status).toEqual({
      code: SpanStatusCode.ERROR,
      message: '42P01',
    });
    expect(
      JSON.stringify([query.attributes, query.events, query.status]),
    ).not.toContain('secret-value');
  });

  it('span 밖의 쿼리는 남기지 않는다', async () => {
    await app.get(DataSource).query('SELECT 1');

    expect(recorder.spans()).toEqual([]);
  });
});

describe('보내는 작업의 span', () => {
  /** 발송함에 알림 하나를 적는다. */
  async function queueOne(): Promise<void> {
    await app
      .get(DataSource)
      .getRepository(OutgoingNotification)
      .insert({
        sourceKey: 'post.commented:1',
        userId: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
        kind: 'post.commented',
        payload: { board_slug: 'free' },
      });
    recorder.clear();
  }

  it('작업의 span 아래에 쿼리와 알림 서버를 부른 span 이 놓이고, 알림 서버에 그 span 이 간다', async () => {
    await queueOne();

    await app.get(NotificationDispatchRunner).runOnce();

    const job = recorder.only('notification.send');
    expect(job.parentSpanContext).toBeUndefined();
    expect(job.attributes).toMatchObject({ handled: 1, result: 'success' });
    const client = recorder.only('HTTP POST');
    expect(parentIdOf(client)).toBe(spanIdOf(job));
    expect(client.attributes['http.response.status_code']).toBe(201);
    const queries = recorder
      .spans()
      .filter((span) => span.name.startsWith('db '));
    expect(queries.map((query) => query.name)).toEqual(
      expect.arrayContaining([
        'db SELECT outgoing_notifications',
        'db DELETE outgoing_notifications',
      ]),
    );
    for (const query of queries) {
      expect(traceIdOf(query)).toBe(traceIdOf(job));
    }
    expect(notifications.received.at(-1)?.traceparent).toBe(
      `00-${traceIdOf(client)}-${spanIdOf(client)}-01`,
    );
  });

  it('그 바퀴의 로그 줄에 job_id 와 그 span 의 trace_id 가 붙는다', async () => {
    await queueOne();

    await app.get(NotificationDispatchRunner).runOnce();

    const job = recorder.only('notification.send');
    const round = lines
      .map((line) => JSON.parse(line) as Record<string, unknown>)
      .find((entry) => entry.operation === 'notification.send');
    expect(round).toMatchObject({
      job_id: job.attributes.job_id,
      trace_id: traceIdOf(job),
      sent: 1,
    });
    expect(round).not.toHaveProperty('request_id');
  });

  it('보낼 것이 없던 바퀴는 아무 span 도 남기지 않는다', async () => {
    await app.get(NotificationDispatchRunner).runOnce();

    expect(recorder.spans()).toEqual([]);
  });
});
