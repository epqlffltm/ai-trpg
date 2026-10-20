// board-server/test/metrics.e2e-spec.ts

/**
 * 앱을 거친 요청이 메트릭으로 세어지는지 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 * 이름과 label 은 docs/observability.md 의 "메트릭"의 표다. 메모리에 모으는 것(test/metrics.ts)으로 읽는다.
 * 검색이 시간을 넘긴 것(timeout)은 search-timeout.e2e-spec.ts 가 본다. 글을 많이 넣어야 한다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { POOL_MAX_CONNECTIONS } from '../src/database/database.options.js';
import { both, createTestApp, useKeys, useWriteLimits } from './app.js';
import { clearData } from './data.js';
import { recordMetrics } from './metrics.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const READER = '5e8f2c1a-9b3d-4e7f-a6c5-1d2e3f4a5b6c';
/** 글은 한 사람이 둘까지, 댓글과 신고는 넉넉히. 셋째 글이 쓰기 횟수 제한에 걸린다 */
const LIMITS = {
  post: { windowSeconds: 600, max: 2 },
  comment: { windowSeconds: 1, max: 1_000_000 },
  report: { windowSeconds: 1, max: 1_000_000 },
};

let app: NestExpressApplication;
let key: SigningKey;
const metrics = recordMetrics();

beforeAll(async () => {
  key = await makeSigningKey('key-1');
  app = await createTestApp(
    both(
      useKeys(() => publicKeys(key)),
      useWriteLimits(LIMITS),
    ),
  );
});

afterAll(async () => {
  await clearData(app);
  await app.close();
});

beforeEach(async () => {
  await clearData(app);
});

/** 이 사람의 토큰을 붙인 머리말. */
async function as(userId: string): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId })}`,
  };
}

/** 자유 게시판에 글을 쓴다. */
async function writePost(userId: string, title = '글') {
  return request(app.getHttpServer())
    .post(`${API}/boards/free/posts`)
    .set(await as(userId))
    .send({ title, content: '본문입니다.' });
}

describe('HTTP 와 DB', () => {
  it('요청을 경로의 틀로 센다. 맞은 것이 없으면 (unmatched) 하나다', async () => {
    await request(app.getHttpServer()).get(`${API}/boards`).expect(200);
    await request(app.getHttpServer()).get('/no/such/secret-path').expect(404);

    expect(
      await metrics.current.value('http_server_requests', {
        method: 'GET',
        route: `${API}/boards`,
        status_code: 200,
      }),
    ).toBe(1);
    expect(
      await metrics.current.value('http_server_requests', {
        route: '(unmatched)',
        status_code: 404,
      }),
    ).toBe(1);
    expect(await metrics.current.value('http_server_active_requests')).toBe(0);
  });

  it('준비 상태 확인이 DB 에 닿았다고 적는다', async () => {
    await request(app.getHttpServer()).get('/health/ready').expect(200);

    expect(await metrics.current.value('db_up')).toBe(1);
  });

  it('앱의 연결 풀을 지켜보고 연결을 기다린 시간을 잰다', async () => {
    await request(app.getHttpServer()).get(`${API}/boards`).expect(200);

    expect(await metrics.current.value('db_pool_connections_max')).toBe(
      POOL_MAX_CONNECTIONS,
    );
    const idle = await metrics.current.value('db_pool_connections', {
      state: 'idle',
    });
    expect(idle).toBeGreaterThanOrEqual(1);
    const [wait] = await metrics.current.points('db_pool_wait');
    expect(wait.value).toBeGreaterThanOrEqual(1);
  });
});

describe('쓰기', () => {
  it('쓴 글, 받지 않은 글, 횟수 제한에 걸린 글을 따로 센다', async () => {
    expect((await writePost(WRITER)).status).toBe(201);
    expect((await writePost(WRITER, '')).status).toBe(400);
    expect((await writePost(WRITER)).status).toBe(201);
    expect((await writePost(WRITER)).status).toBe(429);

    const labels = { resource: 'post', action: 'create' };
    expect(
      await metrics.current.value('board_writes', {
        ...labels,
        result: 'success',
      }),
    ).toBe(2);
    expect(
      await metrics.current.value('board_writes', {
        ...labels,
        result: 'rejected',
      }),
    ).toBe(1);
    expect(
      await metrics.current.value('board_writes', {
        ...labels,
        result: 'rate_limited',
      }),
    ).toBe(1);
  });

  it('남의 댓글을 지우려던 것은 rejected 다', async () => {
    const post = (await writePost(WRITER)).body as { id: string };
    const comment = (
      await request(app.getHttpServer())
        .post(`${API}/posts/${post.id}/comments`)
        .set(await as(WRITER))
        .send({ content: '댓글입니다.' })
        .expect(201)
    ).body as { id: string };

    await request(app.getHttpServer())
      .delete(`${API}/comments/${comment.id}`)
      .set(await as(READER))
      .expect(403);

    expect(
      await metrics.current.value('board_writes', {
        resource: 'comment',
        action: 'create',
        result: 'success',
      }),
    ).toBe(1);
    expect(
      await metrics.current.value('board_writes', {
        resource: 'comment',
        action: 'delete',
        result: 'rejected',
      }),
    ).toBe(1);
  });

  it('로그인하지 않은 쓰기는 쓰기로 세지 않는다', async () => {
    await request(app.getHttpServer())
      .post(`${API}/boards/free/posts`)
      .send({ title: '글', content: '본문입니다.' })
      .expect(401);

    expect(await metrics.current.points('board_writes')).toEqual([]);
  });
});

describe('신고', () => {
  it('받은 신고와 받지 않은 신고(이미 신고함)를 센다', async () => {
    const post = (await writePost(WRITER)).body as { id: string };
    const report = async () =>
      request(app.getHttpServer())
        .post(`${API}/posts/${post.id}/reports`)
        .set(await as(READER))
        .send({ reason: 'spam' });

    expect((await report()).status).toBe(201);
    expect((await report()).status).toBeGreaterThanOrEqual(400);

    expect(
      await metrics.current.value('board_reports', {
        target: 'post',
        result: 'success',
      }),
    ).toBe(1);
    expect(
      await metrics.current.value('board_reports', {
        target: 'post',
        result: 'rejected',
      }),
    ).toBe(1);
  });
});

describe('검색', () => {
  it('검색마다 결과와 걸린 시간을 센다', async () => {
    await request(app.getHttpServer())
      .get(`${API}/posts`)
      .query({ q: '없는낱말' })
      .expect(200);

    expect(
      await metrics.current.value('board_searches', { result: 'success' }),
    ).toBe(1);
    const [duration] = await metrics.current.points('board_search_duration');
    expect(duration).toMatchObject({ unit: 's', value: 1 });
  });
});
