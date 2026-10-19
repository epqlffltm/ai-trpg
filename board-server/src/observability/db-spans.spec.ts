// board-server/src/observability/db-spans.spec.ts

/**
 * 쿼리의 span(db-spans.ts)을 검증한다. DB 에 붙지 않는다. 실제 연결로 거는 것은 test/tracing.e2e-spec.ts 가 본다.
 */

import { SpanKind, SpanStatusCode } from '@opentelemetry/api';
import { parentIdOf, recordSpans, spanIdOf } from '../../test/spans.js';
import {
  operationOf,
  querySpanName,
  queryText,
  returnsPromise,
  sqlState,
  tableOf,
  traceQuery,
  TracedClient,
} from './db-spans.js';
import { tracer } from './spans.js';

const recorder = recordSpans();

describe('문장을 읽는 것', () => {
  it.each([
    [
      'SELECT "Post"."id" FROM "posts" "Post" WHERE "Post"."id" = $1',
      'SELECT',
      'posts',
    ],
    [
      'INSERT INTO "comments"("body") VALUES ($1) RETURNING "id"',
      'INSERT',
      'comments',
    ],
    [
      'UPDATE "outgoing_notifications" SET "attempts" = "attempts" + 1',
      'UPDATE',
      'outgoing_notifications',
    ],
    [
      'DELETE FROM "outgoing_notifications" WHERE "id" = $1',
      'DELETE',
      'outgoing_notifications',
    ],
    ['  select 1', 'SELECT', undefined],
    ['START TRANSACTION', 'START', undefined],
    ['', 'QUERY', undefined],
    ['WITH x AS (SELECT 1) SELECT * FROM x', 'WITH', 'x'],
    ['(SELECT 1)', 'QUERY', undefined],
    ['ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'QUERY', undefined],
  ])('%j 는 %s, 테이블 %s 다', (sql, operation, table) => {
    expect(operationOf(sql)).toBe(operation);
    expect(tableOf(sql)).toBe(table);
  });

  it('span 의 이름은 종류와 테이블이다. 테이블이 없으면 종류만이다', () => {
    expect(querySpanName('SELECT', 'posts')).toBe('db SELECT posts');
    expect(querySpanName('COMMIT', undefined)).toBe('db COMMIT');
  });

  it('pg 에 넘긴 문장을 꺼낸다', () => {
    expect(queryText('SELECT 1')).toBe('SELECT 1');
    expect(queryText({ text: 'SELECT 2', values: [] })).toBe('SELECT 2');
    expect(queryText({ name: 'x' })).toBe('');
    expect(queryText(null)).toBe('');
  });

  it('콜백이나 스트림으로 부른 것은 Promise 로 부른 것이 아니다', () => {
    expect(returnsPromise(['SELECT 1', []])).toBe(true);
    expect(returnsPromise([{ text: 'SELECT 1' }])).toBe(true);
    expect(returnsPromise(['SELECT 1', [], () => undefined])).toBe(false);
    expect(returnsPromise([{ submit: () => undefined }])).toBe(false);
    expect(returnsPromise([{ text: 'SELECT 1', callback: () => 1 }])).toBe(
      false,
    );
  });

  it('SQLSTATE 만 꺼낸다. DB 가 낸 오류가 아니면 error 다', () => {
    expect(sqlState(Object.assign(new Error('dup'), { code: '23505' }))).toBe(
      '23505',
    );
    expect(
      sqlState(Object.assign(new Error('x'), { code: 'ECONNRESET' })),
    ).toBe('error');
    expect(sqlState(new Error('x'))).toBe('error');
    expect(sqlState(null)).toBe('error');
  });
});

describe('traceQuery', () => {
  it('부모 아래에 종류와 테이블만 실은 span 을 건다. 문장과 값은 싣지 않는다', async () => {
    const sql = `SELECT "body" FROM "posts" WHERE "author" = 'secret-user'`;
    await tracer().startActiveSpan('request', async (request) => {
      expect(await traceQuery(sql, () => Promise.resolve('rows'))).toBe('rows');
      request.end();
    });

    const span = recorder.only('db SELECT posts');
    expect(span.kind).toBe(SpanKind.CLIENT);
    expect(parentIdOf(span)).toBe(spanIdOf(recorder.only('request')));
    expect(span.attributes).toEqual({
      'db.system.name': 'postgresql',
      'db.operation.name': 'SELECT',
      'db.collection.name': 'posts',
    });
  });

  it('실패하면 SQLSTATE 만 적고 예외를 그대로 올린다', async () => {
    const failure = Object.assign(
      new Error('duplicate key value (body)=(secret)'),
      { code: '23505' },
    );

    await expect(
      traceQuery('INSERT INTO "posts" VALUES ($1)', () =>
        Promise.reject(failure),
      ),
    ).rejects.toBe(failure);

    expect(recorder.only('db INSERT posts').status).toEqual({
      code: SpanStatusCode.ERROR,
      message: '23505',
    });
  });
});

describe('TracedClient', () => {
  /** pg 의 query 대신 부른 것을 돌려주는 연결. DB 에 붙지 않는다 */
  function clientAnswering(answer: unknown): TracedClient {
    const client = new TracedClient();
    const proto = Object.getPrototypeOf(TracedClient.prototype) as {
      query: (...args: unknown[]) => unknown;
    };
    vi.spyOn(proto, 'query').mockImplementation(() => answer);
    return client;
  }

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('부모 span 이 없으면 pg 의 것을 그대로 부르고 span 을 걸지 않는다', async () => {
    const client = clientAnswering(Promise.resolve({ rows: [] }));

    expect(await client.query('SELECT 1')).toEqual({ rows: [] });
    expect(recorder.spans()).toEqual([]);
  });

  it('부모 span 이 있으면 쿼리마다 span 을 건다', async () => {
    const client = clientAnswering(Promise.resolve({ rows: [1] }));

    await tracer().startActiveSpan('request', async (request) => {
      expect(await client.query('SELECT * FROM "boards"', [])).toEqual({
        rows: [1],
      });
      request.end();
    });

    expect(recorder.named('db SELECT boards')).toHaveLength(1);
  });

  it('콜백으로 부르면 span 없이 pg 의 것을 그대로 부른다', () => {
    const client = clientAnswering(undefined);

    tracer().startActiveSpan('request', (request) => {
      client.query('SELECT 1', [], () => undefined);
      request.end();
    });

    expect(recorder.spans().map((span) => span.name)).toEqual(['request']);
  });
});
