// board-server/src/observability/db-spans.ts

/**
 * 쿼리마다 span 을 건다. TypeORM 이 쓰는 pg 의 연결(Client)을 이 서버의 것으로 바꿔 끼운다
 * (database/database.options.ts 의 extra.Client). pg 의 풀이 연결을 만들 때 이 클래스를 쓴다.
 *
 * pg 를 통째로 고쳐 쓰지(monkey patch) 않는다. 이 서버의 풀이 만든 연결에만 걸린다.
 *
 * 이름은 문장의 종류와 테이블이다(db SELECT posts). 테이블은 문장의 FROM, INTO, UPDATE 뒤의 첫 이름이다.
 * 문장과 값은 싣지 않는다. 값에 글의 본문과 사용자의 번호가 들어간다. 실패하면 SQLSTATE(23505 같은 것)만 적는다.
 * 오류의 글에는 값이 섞일 수 있다.
 *
 * 부모 span 이 기록 중일 때만 건다(요청이나 작업 안의 쿼리). 그 밖의 쿼리(풀이 연결을 맺으며 하는 것)는 남기지 않는다.
 * 콜백이나 스트림으로 부르는 것(TypeORM 의 stream)은 걸지 않고 그대로 넘긴다.
 */

import { SpanKind, SpanStatusCode } from '@opentelemetry/api';
import pg from 'pg';
import { isRecording, tracer } from './spans.js';

/** 쿼리 span 의 이름 앞부분 */
export const SPAN_NAME_PREFIX = 'db ';
/** 종류를 읽지 못한 문장의 이름 */
export const UNKNOWN_OPERATION = 'QUERY';
/** 문장의 종류로 받는 낱말의 가장 긴 길이. 그보다 길면 종류가 아니라고 본다 */
const MAX_OPERATION_LENGTH = 16;
/** 문장의 첫 낱말. 영문자만 받는다 */
const OPERATION = /^[A-Za-z]+$/;
/** 문장이 다루는 첫 테이블. TypeORM 은 이름을 큰따옴표로 감싼다("posts") */
const TABLE_PATTERN = /\b(?:FROM|INTO|UPDATE)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?/i;
/** SQLSTATE 의 모양. 다섯 글자의 영문 대문자와 숫자다 */
const SQL_STATE = /^[0-9A-Z]{5}$/;
/** DB 가 낸 오류가 아닐 때(연결이 끊겼다)의 설명 */
export const UNKNOWN_SQL_STATE = 'error';

/** 문장의 종류(SELECT, INSERT, UPDATE, DELETE). 첫 낱말이다. 읽지 못하면 QUERY 다. */
export function operationOf(sql: string): string {
  const [first = ''] = sql.trim().split(/\s+/, 1);
  if (!OPERATION.test(first) || first.length > MAX_OPERATION_LENGTH) {
    return UNKNOWN_OPERATION;
  }
  return first.toUpperCase();
}

/** 문장이 다루는 첫 테이블. 없으면 undefined 다(SELECT 1, START TRANSACTION). */
export function tableOf(sql: string): string | undefined {
  return TABLE_PATTERN.exec(sql)?.[1];
}

/** 쿼리 span 에 싣는 것. 종류와 테이블뿐이다. */
export function queryAttributes(
  operation: string,
  table: string | undefined,
): Record<string, string> {
  const attributes: Record<string, string> = {
    'db.system.name': 'postgresql',
    'db.operation.name': operation,
  };
  if (table !== undefined) {
    attributes['db.collection.name'] = table;
  }
  return attributes;
}

/** 쿼리 span 의 이름(db SELECT posts). */
export function querySpanName(
  operation: string,
  table: string | undefined,
): string {
  return SPAN_NAME_PREFIX + (table ? `${operation} ${table}` : operation);
}

/** 오류의 SQLSTATE. pg 의 오류는 code 에 둔다. DB 가 낸 오류가 아니면(ECONNRESET 같은 것) error 다. */
export function sqlState(error: unknown): string {
  const code = (error as { code?: unknown } | null)?.code;
  return typeof code === 'string' && SQL_STATE.test(code)
    ? code
    : UNKNOWN_SQL_STATE;
}

/** pg 의 query 에 넘긴 문장. 글자이거나 { text } 다. 읽지 못하면 빈 글자다. */
export function queryText(first: unknown): string {
  if (typeof first === 'string') {
    return first;
  }
  const text = (first as { text?: unknown } | null)?.text;
  return typeof text === 'string' ? text : '';
}

/** 이 부름이 Promise 를 돌려주는가. 콜백이나 스트림(submit 이 있는 것)으로 부르면 아니다. */
export function returnsPromise(args: unknown[]): boolean {
  const first = args[0] as { submit?: unknown; callback?: unknown } | null;
  return (
    typeof args.at(-1) !== 'function' &&
    typeof first?.submit !== 'function' &&
    typeof first?.callback !== 'function'
  );
}

/** 문장 하나를 run 으로 보내는 동안 span 을 건다. 예외는 그대로 올린다. span 에는 SQLSTATE 만 적는다. */
export function traceQuery<Result>(
  sql: string,
  run: () => Promise<Result>,
): Promise<Result> {
  const operation = operationOf(sql);
  const table = tableOf(sql);
  return tracer().startActiveSpan(
    querySpanName(operation, table),
    { kind: SpanKind.CLIENT, attributes: queryAttributes(operation, table) },
    async (span) => {
      try {
        return await run();
      } catch (error) {
        span.setStatus({
          code: SpanStatusCode.ERROR,
          message: sqlState(error),
        });
        throw error;
      } finally {
        span.end();
      }
    },
  );
}

/** 쿼리마다 span 을 거는 pg 의 연결. 부모 span 이 없거나 Promise 로 부르지 않으면 pg 의 것 그대로다. */
export class TracedClient extends pg.Client {
  override query(...args: any[]): any {
    const run = (): Promise<unknown> => Reflect.apply(super.query, this, args);
    if (!isRecording() || !returnsPromise(args)) {
      return run();
    }
    return traceQuery(queryText(args[0]), run);
  }
}
