// board-server/test/write-limits.e2e-spec.ts

/**
 * 쓰기와 신고의 횟수 제한을 앱을 통째로 만들어 불러 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 *
 * 다른 테스트의 앱은 걸리지 않을 만큼 큰 한도를 쓴다(test/app.ts). 여기서는 서버가 쓰는 한도를 그대로 쓴다.
 * 시간이 흘러 창이 지나가는 것은 기다리지 않는다. 쓴 시각을 DB 에서 과거로 옮겨 놓고 본다(test/data.ts).
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { WRITE_LIMITS } from '../src/write-limits/write-limits.policy.js';
import { both, createTestApp, useKeys, useRealWriteLimits } from './app.js';
import { ageWrites, clearData, insertManyPosts, makeOperator } from './data.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;
const POSTS = WRITE_LIMITS.post;
const COMMENTS = WRITE_LIMITS.comment;
const REPORTS = WRITE_LIMITS.report;

/** 테스트에 나오는 사람들. 인증 서버의 public_id 다 */
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const STRANGER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const OPERATOR = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';
const READER = '5e8f2c1a-9b3d-4e7f-a6c5-1d2e3f4a5b6c';

let app: NestExpressApplication;
let key: SigningKey;

beforeAll(async () => {
  key = await makeSigningKey('key-1');
  app = await createTestApp(
    both(
      useKeys(() => publicKeys(key)),
      useRealWriteLimits,
    ),
  );
});

afterAll(async () => {
  await app.close();
});

beforeEach(async () => {
  await clearData(app);
  await makeOperator(app, OPERATOR);
});

/** 이 사람의 토큰을 붙인 머리말. */
async function as(userId: string): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId })}`,
  };
}

/** 글을 쓴다. */
async function writePost(userId: string, board = 'free') {
  return request(app.getHttpServer())
    .post(`${API}/boards/${board}/posts`)
    .set(await as(userId))
    .send({ title: '글', content: '본문입니다.' });
}

/** 글을 n 개 쓴다. 모두 써져야 한다. 마지막에 쓴 글의 번호를 돌려준다. */
async function writePosts(userId: string, n: number): Promise<string> {
  let id = '';
  for (let i = 0; i < n; i += 1) {
    const response = await writePost(userId);
    expect(response.status).toBe(201);
    id = (response.body as { id: string }).id;
  }
  return id;
}

/** 댓글을 단다. parentId 를 주면 답글이다. */
async function writeComment(userId: string, postId: string, parentId?: string) {
  return request(app.getHttpServer())
    .post(`${API}/posts/${postId}/comments`)
    .set(await as(userId))
    .send({ content: '댓글입니다.', parent_id: parentId });
}

/** 댓글을 n 개 단다. 모두 달려야 한다. 마지막에 단 댓글의 번호를 돌려준다. */
async function writeComments(
  userId: string,
  postId: string,
  n: number,
): Promise<string> {
  let id = '';
  for (let i = 0; i < n; i += 1) {
    const response = await writeComment(userId, postId);
    expect(response.status).toBe(201);
    id = (response.body as { id: string }).id;
  }
  return id;
}

/** 게시판의 글 수. */
async function postCount(board = 'free'): Promise<number> {
  const response = await request(app.getHttpServer()).get(
    `${API}/boards/${board}/posts`,
  );
  return (response.body as { total: number }).total;
}

describe('글 쓰기의 한도', () => {
  it('정해 둔 수까지는 쓴다', async () => {
    await writePosts(WRITER, POSTS.max);

    expect(await postCount()).toBe(POSTS.max);
  });

  it('넘기면 429 이고, 기다릴 시간을 본문과 머리말로 알려 준다', async () => {
    await writePosts(WRITER, POSTS.max);

    const response = await writePost(WRITER);

    expect(response.status).toBe(429);
    expect(response.body).toEqual({
      detail: '글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.',
      retry_after: expect.any(Number),
    });
    const retryAfter = (response.body as { retry_after: number }).retry_after;
    expect(Number.isInteger(retryAfter)).toBe(true);
    // 방금 다 썼으니 창의 길이만큼 기다려야 한다
    expect(retryAfter).toBeGreaterThan(POSTS.windowSeconds - 30);
    expect(retryAfter).toBeLessThanOrEqual(POSTS.windowSeconds);
    expect(response.headers['retry-after']).toBe(String(retryAfter));
  });

  it('막힌 글은 저장하지 않는다', async () => {
    await writePosts(WRITER, POSTS.max);

    await writePost(WRITER);

    expect(await postCount()).toBe(POSTS.max);
  });

  it('사람마다 따로 센다', async () => {
    await writePosts(WRITER, POSTS.max);

    expect((await writePost(STRANGER)).status).toBe(201);
  });

  it('시간이 지나 창을 벗어나면 다시 쓴다', async () => {
    await writePosts(WRITER, POSTS.max);

    await ageWrites(app, WRITER, POSTS.windowSeconds + 1);

    expect((await writePost(WRITER)).status).toBe(201);
  });

  it('기다릴 시간은 가장 오래된 글이 창을 벗어날 때까지다', async () => {
    await writePosts(WRITER, 1);
    // 첫 글을 쓴 지 9분이 지났다
    await ageWrites(app, WRITER, POSTS.windowSeconds - 60);
    await writePosts(WRITER, POSTS.max - 1);

    const response = await writePost(WRITER);

    // 1분만 기다리면 첫 글이 창을 벗어나 하나를 더 쓸 수 있다
    const retryAfter = (response.body as { retry_after: number }).retry_after;
    expect(response.status).toBe(429);
    expect(retryAfter).toBeGreaterThan(30);
    expect(retryAfter).toBeLessThanOrEqual(60);
  });

  it('알려 준 시간만큼 기다리면 쓸 수 있다', async () => {
    await writePosts(WRITER, POSTS.max);
    const blocked = await writePost(WRITER);
    const retryAfter = (blocked.body as { retry_after: number }).retry_after;

    await ageWrites(app, WRITER, retryAfter);

    expect((await writePost(WRITER)).status).toBe(201);
  });

  it('쓰고 지워도 쓴 것으로 센다', async () => {
    const last = await writePosts(WRITER, POSTS.max);
    await request(app.getHttpServer())
      .delete(`${API}/posts/${last}`)
      .set(await as(WRITER));

    // 지워서 자리를 낼 수 있으면 "쓰고 지우고 또 쓰기"로 한도를 피한다
    expect((await writePost(WRITER)).status).toBe(429);
  });

  it('운영자는 걸리지 않는다', async () => {
    await writePosts(OPERATOR, POSTS.max);

    expect((await writePost(OPERATOR)).status).toBe(201);
    expect((await writePost(OPERATOR, 'notice')).status).toBe(201);
  });

  it('쓸 수 없는 게시판이면 한도를 넘겼어도 403 이 먼저다', async () => {
    await writePosts(WRITER, POSTS.max);

    expect((await writePost(WRITER, 'notice')).status).toBe(403);
  });

  it('댓글을 많이 달아도 글의 한도에는 세지 않는다', async () => {
    const postId = await writePosts(WRITER, 1);
    await writeComments(WRITER, postId, COMMENTS.max);

    expect((await writePost(WRITER)).status).toBe(201);
  });

  it('고치기와 지우기는 세지 않는다', async () => {
    const last = await writePosts(WRITER, POSTS.max);

    const edited = await request(app.getHttpServer())
      .patch(`${API}/posts/${last}`)
      .set(await as(WRITER))
      .send({ title: '고친 제목' });

    expect(edited.status).toBe(200);
  });
});

describe('댓글 쓰기의 한도', () => {
  let postId: string;

  beforeEach(async () => {
    postId = await writePosts(STRANGER, 1);
  });

  it('정해 둔 수까지는 달고, 넘기면 429 다', async () => {
    await writeComments(WRITER, postId, COMMENTS.max);

    const response = await writeComment(WRITER, postId);

    expect(response.status).toBe(429);
    expect(response.body).toEqual({
      detail: '댓글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.',
      retry_after: expect.any(Number),
    });
    const retryAfter = (response.body as { retry_after: number }).retry_after;
    expect(retryAfter).toBeGreaterThan(COMMENTS.windowSeconds - 30);
    expect(retryAfter).toBeLessThanOrEqual(COMMENTS.windowSeconds);
    expect(response.headers['retry-after']).toBe(String(retryAfter));
  });

  it('답글도 함께 센다', async () => {
    const parent = await writeComments(WRITER, postId, 1);
    for (let i = 1; i < COMMENTS.max; i += 1) {
      expect((await writeComment(WRITER, postId, parent)).status).toBe(201);
    }

    expect((await writeComment(WRITER, postId, parent)).status).toBe(429);
  });

  it('여러 글에 나눠 달아도 함께 센다', async () => {
    const other = await writePosts(STRANGER, 1);
    await writeComments(WRITER, postId, COMMENTS.max - 1);
    await writeComments(WRITER, other, 1);

    expect((await writeComment(WRITER, other)).status).toBe(429);
  });

  it('사람마다 따로 센다', async () => {
    await writeComments(WRITER, postId, COMMENTS.max);

    expect((await writeComment(STRANGER, postId)).status).toBe(201);
  });

  it('시간이 지나 창을 벗어나면 다시 단다', async () => {
    await writeComments(WRITER, postId, COMMENTS.max);

    await ageWrites(app, WRITER, COMMENTS.windowSeconds + 1);

    expect((await writeComment(WRITER, postId)).status).toBe(201);
  });

  it('달고 지워도 단 것으로 센다', async () => {
    const last = await writeComments(WRITER, postId, COMMENTS.max);
    await request(app.getHttpServer())
      .delete(`${API}/comments/${last}`)
      .set(await as(WRITER));

    expect((await writeComment(WRITER, postId)).status).toBe(429);
  });

  it('운영자는 걸리지 않는다', async () => {
    await writeComments(OPERATOR, postId, COMMENTS.max);

    expect((await writeComment(OPERATOR, postId)).status).toBe(201);
  });

  it('없는 글이면 한도를 넘겼어도 404 가 먼저다', async () => {
    await writeComments(WRITER, postId, COMMENTS.max);

    expect((await writeComment(WRITER, '999')).status).toBe(404);
  });

  it('글을 많이 써도 댓글의 한도에는 세지 않는다', async () => {
    await writePosts(WRITER, POSTS.max);

    expect((await writeComment(WRITER, postId)).status).toBe(201);
  });
});

describe('신고의 한도', () => {
  beforeEach(async () => {
    // 신고할 글을 넉넉히 넣는다. API 를 거치면 글 쓰기의 한도에 걸린다
    await insertManyPosts(app, REPORTS.max + 2, STRANGER);
  });

  /** n 번 글을 신고한다. */
  async function report(userId: string, postId: number) {
    return request(app.getHttpServer())
      .post(`${API}/posts/${postId}/reports`)
      .set(await as(userId))
      .send({ reason: 'spam' });
  }

  /** 1 번 글부터 n 개를 신고한다. 모두 접수돼야 한다. */
  async function reportMany(userId: string, n: number): Promise<void> {
    for (let id = 1; id <= n; id += 1) {
      expect((await report(userId, id)).status).toBe(201);
    }
  }

  it('정해 둔 수까지는 신고하고, 넘기면 429 다', async () => {
    await reportMany(WRITER, REPORTS.max);

    const response = await report(WRITER, REPORTS.max + 1);

    expect(response.status).toBe(429);
    expect(response.body).toEqual({
      detail: '신고를 너무 자주 하고 있습니다. 잠시 후 다시 시도해 주세요.',
      retry_after: expect.any(Number),
    });
    const retryAfter = (response.body as { retry_after: number }).retry_after;
    expect(retryAfter).toBeGreaterThan(REPORTS.windowSeconds - 30);
    expect(retryAfter).toBeLessThanOrEqual(REPORTS.windowSeconds);
    expect(response.headers['retry-after']).toBe(String(retryAfter));
  });

  it('시간이 지나 창을 벗어나면 다시 신고한다', async () => {
    await reportMany(WRITER, REPORTS.max);

    await ageWrites(app, WRITER, REPORTS.windowSeconds + 1);

    expect((await report(WRITER, REPORTS.max + 1)).status).toBe(201);
  });

  it('사람마다 따로 센다', async () => {
    await reportMany(WRITER, REPORTS.max);

    expect((await report(READER, 1)).status).toBe(201);
  });

  it('운영자는 걸리지 않는다', async () => {
    await reportMany(OPERATOR, REPORTS.max);

    expect((await report(OPERATOR, REPORTS.max + 1)).status).toBe(201);
  });

  it('이미 신고한 것이면 한도를 넘겼어도 409 가 먼저다', async () => {
    await reportMany(WRITER, REPORTS.max);

    expect((await report(WRITER, 1)).status).toBe(409);
  });

  it('글과 댓글을 많이 써도 신고의 한도에는 세지 않는다', async () => {
    const postId = await writePosts(WRITER, POSTS.max);
    await writeComments(WRITER, postId, COMMENTS.max);

    expect((await report(WRITER, 1)).status).toBe(201);
  });
});
