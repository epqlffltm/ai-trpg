// board-server/src/observability/json-logger.spec.ts

/**
 * 로그 한 줄이 공통 규격의 JSON 으로 나가는지, 민감한 값이 가려지는지 검증한다(json-logger.ts, redaction.ts).
 * 규격은 저장소 루트의 docs/observability.md 에 있다.
 */

import { Logger } from '@nestjs/common';
import { newTrace } from './identifiers.js';
import {
  isLevelEnabled,
  JsonLogger,
  LogLevel,
  messageOf,
  splitParams,
} from './json-logger.js';
import {
  isSensitiveName,
  MAX_VALUE_LENGTH,
  REDACTED,
  safeValue,
  scrubText,
} from './redaction.js';
import { runInRequest } from './request-context.js';

const INFO = {
  service: 'board-server',
  environment: 'test',
  version: 'test-version',
};
const NOW = new Date('2026-10-11T09:00:00.123Z');
// 서명까지 갖춘 토큰의 모양. 실제 키로 만든 것이 아니다
const JWT =
  'eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVlLWhlcmU';

/** 내보낸 줄을 모으는 로거. lines 는 나간 그대로의 글, entries 는 그것을 다시 읽은 것이다. */
function makeLogger(threshold: LogLevel = 'debug') {
  const lines: string[] = [];
  const logger = new JsonLogger(
    INFO,
    threshold,
    (line) => lines.push(line),
    () => NOW,
  );
  const entries = () =>
    lines.map((line) => JSON.parse(line) as Record<string, unknown>);
  return { logger, lines, entries };
}

/** 로그 한 줄을 남기고 나간 것을 돌려준다. */
function logged(message: unknown, ...params: unknown[]) {
  const { logger, entries } = makeLogger();
  logger.log(message, ...params);
  return entries()[0];
}

describe('JsonLogger', () => {
  it('모든 줄에 공통 칸이 있다', () => {
    const entry = logged('서버가 떴다', 'NestApplication');

    expect(entry).toEqual({
      timestamp: '2026-10-11T09:00:00.123Z',
      level: 'info',
      service: 'board-server',
      environment: 'test',
      version: 'test-version',
      logger: 'NestApplication',
      message: '서버가 떴다',
    });
  });

  it('한 줄에 JSON 하나다', () => {
    const { logger, lines } = makeLogger();

    logger.log('첫 줄\n{"level":"error","message":"가짜 줄"}');

    // 메시지에 줄바꿈을 넣어도 로그는 한 줄이다. 가짜 로그 줄을 끼워 넣을 수 없다
    expect(lines).toHaveLength(1);
    expect(lines[0]).not.toContain('\n');
  });

  it.each([
    ['debug', 'debug'],
    ['verbose', 'debug'],
    ['log', 'info'],
    ['warn', 'warning'],
    ['error', 'error'],
    ['fatal', 'critical'],
  ] as const)('Nest 의 %s 는 규격의 %s 다', (method, level) => {
    const { logger, entries } = makeLogger();

    logger[method]('글');

    expect(entries()[0].level).toBe(level);
  });

  it('남기는 수준보다 낮은 것은 내보내지 않는다', () => {
    const { logger, entries } = makeLogger('warning');

    logger.debug('디버그');
    logger.log('정보');
    logger.warn('경고');
    logger.error('오류');

    expect(entries().map((entry) => entry.message)).toEqual(['경고', '오류']);
  });

  it('객체로 넘긴 칸을 싣는다', () => {
    const entry = logged({
      message: '요청을 처리했다',
      operation: 'http.request',
      duration_ms: 12,
      result: 'success',
      retried: false,
    });

    expect(entry).toMatchObject({
      message: '요청을 처리했다',
      operation: 'http.request',
      duration_ms: 12,
      result: 'success',
      retried: false,
    });
  });

  it('걸려 있는 식별자를 붙인다', () => {
    const { logger, entries } = makeLogger();
    const trace = newTrace();

    runInRequest({ requestId: 'request-12345', trace }, () =>
      logger.log('요청 안'),
    );
    logger.log('요청 밖');

    const [inside, outside] = entries();
    expect(inside.request_id).toBe('request-12345');
    expect(inside.trace_id).toBe(trace.traceId);
    // 걸려 있지 않은 식별자는 빈 글자로 채우지 않고 싣지 않는다
    expect(outside).not.toHaveProperty('request_id');
    expect(outside).not.toHaveProperty('trace_id');
  });

  it('걸려 있는 식별자는 객체의 칸으로 바꿔 적을 수 없다', () => {
    const { logger, entries } = makeLogger();

    runInRequest({ requestId: 'request-12345', trace: newTrace() }, () =>
      logger.log({ message: '글', request_id: 'forged-request-id' }),
    );

    expect(entries()[0].request_id).toBe('request-12345');
  });

  it('이 서버가 정하는 칸은 덮어쓸 수 없다', () => {
    const entry = logged({
      message: '글',
      service: 'other-server',
      environment: 'production',
      version: '9.9.9',
      level: 'debug',
      timestamp: '1999-01-01T00:00:00.000Z',
    });

    expect(entry).toMatchObject({
      service: 'board-server',
      environment: 'test',
      version: 'test-version',
      level: 'info',
      timestamp: '2026-10-11T09:00:00.123Z',
    });
  });

  it('예외의 기록(stack)을 싣는다', () => {
    const { logger, entries } = makeLogger();
    const failure = new RangeError('버그');

    logger.error(
      { message: failure.message, error_code: 'http.unhandled_exception' },
      failure.stack,
      'AllExceptionsFilter',
    );

    const [entry] = entries();
    expect(entry.level).toBe('error');
    expect(entry.logger).toBe('AllExceptionsFilter');
    expect(entry.error_code).toBe('http.unhandled_exception');
    expect(entry.stack_trace).toContain('RangeError: 버그');
    expect(entry.stack_trace).toContain('json-logger.spec.ts');
  });

  it('Nest 의 Logger 를 거쳐 남긴 것도 같은 모양으로 나간다', () => {
    const { logger, entries } = makeLogger();
    Logger.overrideLogger(logger);

    new Logger('PostsService').warn('글을 저장하지 못했다');
    Logger.overrideLogger(['warn', 'error', 'fatal']);

    expect(entries()[0]).toMatchObject({
      level: 'warning',
      logger: 'PostsService',
      message: '글을 저장하지 못했다',
    });
  });
});

describe('민감한 값 가리기', () => {
  it.each([
    'password',
    'new_password',
    'token',
    'access_token',
    'refreshToken',
    'jwt',
    'authorization',
    'Authorization',
    'cookie',
    'Set-Cookie',
    'secret',
    'api_key',
    'apiKey',
    'private_key',
    'database_url',
    'DATABASE_URL',
    'dsn',
    'email',
    'user_email',
    'code',
    'invite_code',
    'otp',
    'prompt',
    'card_number',
    'payment_key',
    'signature',
    'body',
    'content',
    'title',
    'text',
    'headers',
  ])('민감한 이름의 칸(%s)은 값을 가린다', (name) => {
    expect(isSensitiveName(name)).toBe(true);
    expect(logged({ message: '글', [name]: '드러나면 안 되는 값' })[name]).toBe(
      REDACTED,
    );
  });

  it.each([
    'operation',
    'status_code',
    'error_code',
    'duration_ms',
    'result',
    'route',
    'method',
    'email_hash',
    'post_id',
    'token_type',
    'error_type',
  ])('평범한 이름의 칸(%s)은 그대로 둔다', (name) => {
    expect(isSensitiveName(name)).toBe(false);
  });

  it('메시지에 든 토큰을 가린다', () => {
    const entry = logged(`토큰을 검증하지 못했다: ${JWT}`);

    expect(JSON.stringify(entry)).not.toContain(JWT);
    expect(entry.message).toContain('[REDACTED_JWT]');
  });

  it('어느 칸에 있든 Authorization 의 값을 가린다', () => {
    const entry = logged({
      message: '요청',
      detail: `Authorization: Bearer ${JWT}`,
      hint: 'Basic dXNlcjpwYXNzd29yZA==',
    });

    const text = JSON.stringify(entry);
    expect(text).not.toContain(JWT);
    expect(text).not.toContain('dXNlcjpwYXNzd29yZA==');
  });

  it('주소에 든 계정과 비밀번호를 가린다', () => {
    const entry = logged(
      'DB 에 닿지 않는다: postgresql://board:super-secret@db.internal:5432/trpg',
    );

    expect(entry.message).not.toContain('super-secret');
    expect(entry.message).not.toContain('board:');
    // 어디에 닿지 못했는지는 남는다
    expect(entry.message).toContain('db.internal');
  });

  it('이메일 주소를 가린다', () => {
    const entry = logged('메일을 보내지 못했다: someone.private@example.com');

    expect(entry.message).not.toContain('someone.private');
    expect(entry.message).toContain('s***@example.com');
  });

  it('예외의 기록에 든 비밀값을 가린다', () => {
    const { logger, entries } = makeLogger();

    logger.error(
      '실패했다',
      `Error: connect failed: postgresql://board:super-secret@db/trpg ${JWT}\n    at somewhere`,
      'Context',
    );

    const stack = entries()[0].stack_trace as string;
    expect(stack).not.toContain('super-secret');
    expect(stack).not.toContain(JWT);
  });

  it.each([
    [{ password: 'p' }, '[Object]'],
    [['a', 'b'], '[Array]'],
    [new Map([['a', 1]]), '[Map]'],
    [new Error('글'), '[Error]'],
    [() => 'secret', '[function]'],
  ])('묶음(%j)은 풀어 적지 않는다', (value, kind) => {
    // 종류의 이름만 남는다
    expect(logged({ message: '글', payload: value }).payload).toBe(kind);
  });

  it('글자, 숫자, 참거짓은 그대로 싣는다', () => {
    expect(safeValue('count', 3)).toBe(3);
    expect(safeValue('ratio', 0.5)).toBe(0.5);
    expect(safeValue('retried', true)).toBe(true);
    expect(safeValue('reason', null)).toBeNull();
    expect(safeValue('post_id', 9007199254740993n)).toBe('9007199254740993');
    // JSON 에 없는 숫자는 글자로 적는다
    expect(safeValue('ratio', Number.NaN)).toBe('NaN');
    // 값이 없는 칸은 싣지 않는다
    expect(safeValue('reason', undefined)).toBeUndefined();
  });

  it('긴 값은 자른다', () => {
    const value = scrubText('가'.repeat(MAX_VALUE_LENGTH + 100));

    expect(value).toHaveLength(MAX_VALUE_LENGTH + 1);
    expect(value.endsWith('…')).toBe(true);
  });
});

describe('isLevelEnabled', () => {
  it('정한 수준부터 남긴다', () => {
    expect(isLevelEnabled('info', 'info')).toBe(true);
    expect(isLevelEnabled('error', 'info')).toBe(true);
    expect(isLevelEnabled('debug', 'info')).toBe(false);
    expect(isLevelEnabled('critical', 'error')).toBe(true);
  });
});

describe('messageOf', () => {
  it('글자, 객체, 오류에서 메시지를 꺼낸다', () => {
    expect(messageOf('글')).toBe('글');
    expect(messageOf({ message: '객체의 글' })).toBe('객체의 글');
    expect(messageOf({ operation: 'http.request' })).toBe('');
    expect(messageOf(new RangeError('버그'))).toBe('RangeError: 버그');
    expect(messageOf(42)).toBe('42');
  });
});

describe('splitParams', () => {
  it('Nest 가 넘기는 것에서 context 와 stack 을 가린다', () => {
    expect(splitParams([])).toEqual({});
    expect(splitParams(['Context'])).toEqual({ context: 'Context' });
    expect(splitParams(['Error: x\n    at y', 'Context'])).toEqual({
      context: 'Context',
      stack: 'Error: x\n    at y',
    });
  });
});
