// board-server/test/observability.e2e-spec.ts

/**
 * 요청마다 식별자가 걸리고 끝나면 공통 규격의 한 줄이 남는지 앱을 통째로 만들어 본다.
 * 서버가 쓰는 것과 같은 로거(JsonLogger)를 꽂아, 실제로 나가는 줄을 모아서 본다.
 * 규격은 저장소 루트의 docs/observability.md 에 있다.
 */

import { Controller, Get, Module } from '@nestjs/common';
import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { loadKeys } from '../src/auth/jwks.js';
import { Public } from '../src/auth/public.decorator.js';
import { parseTraceparent } from '../src/observability/identifiers.js';
import { JsonLogger } from '../src/observability/json-logger.js';
import { runInRequest } from '../src/observability/request-context.js';
import { createTestApp, useKeys } from './app.js';
import { clearData } from './data.js';
import {
  jwksDocument,
  makeSigningKey,
  publicKeys,
  SigningKey,
  signToken,
} from './tokens.js';

const API = `/${API_PREFIX}`;
const TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736';
const TRACEPARENT = `00-${TRACE_ID}-00f067aa0ba902b7-01`;
const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
// 예외의 글에 든, 응답과 로그에 실리면 안 되는 값
const SECRET_IN_ERROR = 'postgresql://board:super-secret@db.internal:5432/trpg';

/** 처리하지 못한 예외를 내는 컨트롤러. */
@Public()
@Controller('broken')
class BrokenController {
  @Get(':id')
  read(): never {
    throw new RangeError(`connect failed: ${SECRET_IN_ERROR}`);
  }
}

@Module({ controllers: [BrokenController] })
class ProbeModule {}

let app: NestExpressApplication;
let key: SigningKey;
/** 서버가 내보낸 로그 줄들. 테스트마다 비운다 */
let lines: string[];

beforeAll(async () => {
  key = await makeSigningKey('key-1');
  app = await createTestApp(
    useKeys(() => publicKeys(key)),
    [ProbeModule],
  );
  // 서버가 쓰는 것과 같은 로거를 꽂는다. 나가는 줄을 표준 오류 대신 목록에 모은다
  app.useLogger(
    new JsonLogger(
      { service: 'board-server', environment: 'test', version: 'test-version' },
      'debug',
      (line) => lines.push(line),
    ),
  );
});

afterAll(async () => {
  app.useLogger(['warn', 'error', 'fatal']);
  await app.close();
});

beforeEach(async () => {
  lines = [];
  await clearData(app);
});

/** 나간 줄들을 다시 읽는다. */
function entries(): Record<string, unknown>[] {
  return lines.map((line) => JSON.parse(line) as Record<string, unknown>);
}

/** 요청이 끝났다는 줄. 하나여야 한다. */
function finishedLine(): Record<string, unknown> {
  const finished = entries().filter((entry) => 'status_code' in entry);
  expect(finished).toHaveLength(1);
  return finished[0];
}

describe('요청 식별자', () => {
  it('식별자가 없는 요청에 새 식별자를 주고 응답에 돌려준다', async () => {
    const response = await request(app.getHttpServer()).get('/health');

    expect(response.headers['x-request-id']).toMatch(UUID);
  });

  it('요청마다 다른 식별자를 준다', async () => {
    const first = await request(app.getHttpServer()).get('/health');
    const second = await request(app.getHttpServer()).get('/health');

    expect(first.headers['x-request-id']).not.toBe(
      second.headers['x-request-id'],
    );
  });

  it('형식에 맞는 식별자는 그대로 쓴다', async () => {
    const response = await request(app.getHttpServer())
      .get('/health')
      .set('X-Request-ID', 'client-chosen-id-0001');

    expect(response.headers['x-request-id']).toBe('client-chosen-id-0001');
    expect(finishedLine().request_id).toBe('client-chosen-id-0001');
  });

  it.each([
    'short',
    'a'.repeat(65),
    'a'.repeat(3000),
    'has space in it',
    '{"level":"error"}',
    'semi;colon-12345',
  ])('형식에 맞지 않는 식별자(%j)는 새것으로 바꾼다', async (value) => {
    const response = await request(app.getHttpServer())
      .get('/health')
      .set('X-Request-ID', value);

    expect(response.headers['x-request-id']).toMatch(UUID);
    // 받은 값은 응답에도 로그에도 남지 않는다
    expect(lines.join('\n')).not.toContain(value);
  });

  it('추적은 부른 쪽의 것을 이어 간다', async () => {
    await request(app.getHttpServer())
      .get('/health')
      .set('traceparent', TRACEPARENT);

    expect(finishedLine().trace_id).toBe(TRACE_ID);
  });

  it('로그인하지 못한 요청과 없는 주소에도 식별자를 돌려준다', async () => {
    const unauthorized = await request(app.getHttpServer()).get(`${API}/me`);
    const missing = await request(app.getHttpServer()).get('/no/such/address');

    expect(unauthorized.status).toBe(401);
    expect(unauthorized.headers['x-request-id']).toMatch(UUID);
    expect(missing.status).toBe(404);
    expect(missing.headers['x-request-id']).toMatch(UUID);
  });
});

describe('요청이 끝난 줄', () => {
  it('공통 칸이 모두 있다', async () => {
    // 상태 확인 주소가 아닌 보통의 주소로 본다. 상태 확인의 줄은 수준이 다르다(아래)
    const response = await request(app.getHttpServer()).get(`${API}/boards`);

    const line = finishedLine();
    expect(line).toMatchObject({
      level: 'info',
      service: 'board-server',
      environment: 'test',
      version: 'test-version',
      operation: 'http.request',
      method: 'GET',
      route: `${API}/boards`,
      status_code: 200,
      result: 'success',
      request_id: response.headers['x-request-id'],
    });
    expect(line.timestamp).toMatch(
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/,
    );
    expect(line.trace_id).toMatch(/^[0-9a-f]{32}$/);
    expect(Number.isInteger(line.duration_ms)).toBe(true);
  });

  it('경로는 실제 주소가 아니라 틀로 적는다', async () => {
    const response = await request(app.getHttpServer()).get(
      `${API}/posts/987654321?secret=query-value`,
    );

    const line = finishedLine();
    expect(response.status).toBe(404);
    expect(line.route).toBe(`${API}/posts/:id`);
    // 주소에 든 글 번호와 주소 뒤에 붙인 값은 남지 않는다
    expect(JSON.stringify(line)).not.toContain('987654321');
    expect(JSON.stringify(line)).not.toContain('query-value');
  });

  it('요청의 잘못(4xx)은 info 고, 결과는 client_error 다', async () => {
    await request(app.getHttpServer()).get(`${API}/me`);

    // 요청이 틀린 것이다. 서버는 제 일을 했다. 경고로 올리지 않는다
    expect(finishedLine()).toMatchObject({
      status_code: 401,
      result: 'client_error',
      level: 'info',
    });
  });

  it('없는 주소는 틀 자리에 표시를 적고 실제 경로를 따로 싣는다', async () => {
    await request(app.getHttpServer()).get('/no/such/address?x=query-value');

    const line = finishedLine();
    expect(line.route).toBe('(unmatched)');
    expect(line.path).toBe('/no/such/address');
    expect(JSON.stringify(line)).not.toContain('query-value');
  });

  it('토큰, 쿠키, 요청의 본문은 로그에 남지 않는다', async () => {
    const token = await signToken(key);

    const response = await request(app.getHttpServer())
      .post(`${API}/boards/free/posts`)
      .set('Authorization', `Bearer ${token}`)
      .set('Cookie', 'refresh_token=cookie-secret-value')
      .send({ title: '남기면 안 되는 제목', content: '남기면 안 되는 본문' });

    expect(response.status).toBe(201);
    const everything = lines.join('\n');
    expect(everything).not.toContain(token);
    expect(everything).not.toContain('cookie-secret-value');
    expect(everything).not.toContain('남기면 안 되는');
  });

  it('토큰에 실린 닉네임은 로그에 남지 않는다. 사람은 번호로만 적는다', async () => {
    const token = await signToken(key, { nickname: '로그에없을이름' });

    const response = await request(app.getHttpServer())
      .post(`${API}/boards/free/posts`)
      .set('Authorization', `Bearer ${token}`)
      .send({ title: '제목', content: '본문' });

    expect(response.status).toBe(201);
    expect(lines.join('\n')).not.toContain('로그에없을이름');
  });

  it('신고의 설명은 접수, 다시 신고(409), 입력 오류(400) 어디서도 로그와 응답에 남지 않는다', async () => {
    const writer = `Bearer ${await signToken(key)}`;
    const reporter = `Bearer ${await signToken(key, { subject: '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a' })}`;
    const posted = await request(app.getHttpServer())
      .post(`${API}/boards/free/posts`)
      .set('Authorization', writer)
      .send({ title: '제목', content: '본문' });
    const reportUrl = `${API}/posts/${(posted.body as { id: string }).id}/reports`;
    const secret = '남기면 안 되는 신고의 설명';

    const responses = [
      await request(app.getHttpServer())
        .post(reportUrl)
        .set('Authorization', reporter)
        .send({ reason: 'abuse', description: secret }),
      await request(app.getHttpServer())
        .post(reportUrl)
        .set('Authorization', reporter)
        .send({ reason: 'abuse', description: secret }),
      await request(app.getHttpServer())
        .post(reportUrl)
        .set('Authorization', reporter)
        .send({ reason: 'abuse', description: `${secret}${'a'.repeat(600)}` }),
    ];

    expect(responses.map((response) => response.status)).toEqual([
      201, 409, 400,
    ]);
    for (const response of responses) {
      expect(JSON.stringify(response.body)).not.toContain(secret);
    }
    expect(lines.join('\n')).not.toContain(secret);
  });
});

describe('처리하지 못한 예외', () => {
  it('요청의 식별자와 함께 공통 규격으로 남는다', async () => {
    const response = await request(app.getHttpServer())
      .get(`${API}/broken/thing-1234`)
      .set('traceparent', TRACEPARENT);

    const errorLines = entries().filter((entry) => 'stack_trace' in entry);
    expect(errorLines).toHaveLength(1);
    expect(errorLines[0]).toMatchObject({
      level: 'error',
      request_id: response.headers['x-request-id'],
      trace_id: TRACE_ID,
      operation: 'http.request',
      error_code: 'http.unhandled_exception',
      error_type: 'RangeError',
    });
    expect(errorLines[0].stack_trace).toContain('RangeError');
    // 예외의 글에 든 비밀번호는 로그에서도 가려진다
    expect(lines.join('\n')).not.toContain('super-secret');
  });

  it('요청이 끝난 줄은 error 고, 결과는 server_error 다', async () => {
    await request(app.getHttpServer()).get(`${API}/broken/thing-1234`);

    expect(finishedLine()).toMatchObject({
      status_code: 500,
      result: 'server_error',
      level: 'error',
      route: `${API}/broken/:id`,
    });
  });

  it('응답에는 예외의 내용을 싣지 않고 식별자만 돌려준다', async () => {
    const response = await request(app.getHttpServer()).get(
      `${API}/broken/thing-1234`,
    );

    expect(response.status).toBe(500);
    expect(response.body).toEqual({ detail: '서버에서 오류가 났습니다.' });
    expect(response.text).not.toContain('super-secret');
    expect(response.text).not.toContain('RangeError');
    expect(response.headers['x-request-id']).toMatch(UUID);
  });
});

describe('다른 서버를 부를 때', () => {
  it('인증 서버에 추적을 이어 주고, 요청의 식별자는 넘기지 않는다', async () => {
    const seen: Headers[] = [];
    const fetcher: typeof fetch = (_url, init) => {
      seen.push(new Headers(init?.headers));
      return Promise.resolve(Response.json(jwksDocument(key)));
    };
    const trace = { traceId: TRACE_ID, flags: '01' };

    await runInRequest({ requestId: 'request-12345', trace }, () =>
      loadKeys('http://auth.invalid/jwks', fetcher),
    );

    expect(parseTraceparent(seen[0].get('traceparent'))).toEqual(trace);
    // 받는 서버가 제 요청의 식별자를 따로 만든다
    expect(seen[0].has('x-request-id')).toBe(false);
  });

  it('요청 밖에서 부르면 추적을 붙이지 않는다', async () => {
    const seen: Headers[] = [];
    const fetcher: typeof fetch = (_url, init) => {
      seen.push(new Headers(init?.headers));
      return Promise.resolve(Response.json(jwksDocument(key)));
    };

    await loadKeys('http://auth.invalid/jwks', fetcher);

    expect(seen[0].has('traceparent')).toBe(false);
  });
});

describe('상태를 확인하는 주소', () => {
  it.each(['/health', '/health/ready'])(
    '%s 의 성공은 debug 로 남는다',
    async (url) => {
      await request(app.getHttpServer()).get(url);

      // 관리 도구가 10초마다 부른다. 운영의 수준(info)에서는 남지 않는다
      expect(finishedLine()).toMatchObject({
        level: 'debug',
        route: url,
        status_code: 200,
      });
    },
  );

  it('HEAD 에는 본문 없이 GET 과 같은 상태 코드로 답한다', async () => {
    const health = await request(app.getHttpServer()).head('/health');
    const ready = await request(app.getHttpServer()).head('/health/ready');

    expect([health.status, ready.status]).toEqual([200, 200]);
    expect([health.text, ready.text]).toEqual([undefined, undefined]);
  });

  it('본문의 모양은 그대로다. 식별자는 머리말로만 돌려준다', async () => {
    const health = await request(app.getHttpServer()).get('/health');
    const ready = await request(app.getHttpServer()).get('/health/ready');

    expect(health.body).toEqual({ status: 'ok' });
    expect(ready.body).toEqual({ status: 'ok' });
  });
});
