// board-server/test/reports.e2e-spec.ts

/**
 * 신고의 API 를 앱을 통째로 만들어 불러 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 *
 * 신고하기(로그인한 누구나)와 읽고 처리하기(운영자)를 함께 본다. 횟수 제한은 write-limits.e2e-spec.ts 가 본다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { DataSource } from 'typeorm';
import { API_PREFIX } from '../src/app.setup.js';
import {
  DESCRIPTION_MAX_LENGTH,
  REPORT_REASONS,
} from '../src/reports/reports.policy.js';
import { createTestApp, useKeys } from './app.js';
import { clearData, makeOperator, readReportRow } from './data.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;

/** 테스트에 나오는 사람들. 인증 서버의 public_id 다 */
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const READER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const ANOTHER = '5e8f2c1a-9b3d-4e7f-a6c5-1d2e3f4a5b6c';
const THIRD = '9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d';
const OPERATOR = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';

/** 사유마다 0 건. 운영자의 목록에서 견줄 때 쓴다 */
const NO_REASONS = Object.fromEntries(
  REPORT_REASONS.map((reason) => [reason, 0]),
);

/** 운영자의 목록 한 줄에서 테스트가 읽는 칸. */
interface Group {
  target: { type: string; id: string; post_id: string; deleted: boolean };
  open_count: number;
  reasons: Record<string, number>;
  first_reported_at: string;
  last_reported_at: string;
}

/** 쪽으로 나눈 목록. */
interface Listing<Item> {
  items: Item[];
  page: number;
  size: number;
  total: number;
}

/** 운영자가 읽는 신고 한 건에서 테스트가 읽는 칸. */
interface ReportItem {
  id: string;
  reason: string;
  description: string | null;
  reporter_id: string;
  handled_at: string | null;
  handled_by: string | null;
  outcome: string | null;
}

let app: NestExpressApplication;
let key: SigningKey;

beforeAll(async () => {
  key = await makeSigningKey('key-1');
  app = await createTestApp(useKeys(() => publicKeys(key)));
});

afterAll(async () => {
  await app.close();
});

beforeEach(async () => {
  await clearData(app);
  makeOperator(OPERATOR);
});

/** 이 사람의 토큰을 붙인 머리말. */
async function as(userId: string): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId })}`,
  };
}

/** 글을 써서 그 번호를 돌려준다. */
async function writtenPost(userId = WRITER): Promise<string> {
  const response = await request(app.getHttpServer())
    .post(`${API}/boards/free/posts`)
    .set(await as(userId))
    .send({ title: '글', content: '본문입니다.' });
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 댓글을 달아 그 번호를 돌려준다. parentId 를 주면 답글이다. */
async function writtenComment(
  postId: string,
  userId = WRITER,
  parentId?: string,
): Promise<string> {
  const response = await request(app.getHttpServer())
    .post(`${API}/posts/${postId}/comments`)
    .set(await as(userId))
    .send({ content: '댓글입니다.', parent_id: parentId });
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 글이나 댓글을 신고한다. kind 는 주소의 앞부분(posts, comments)이다. */
async function report(
  userId: string,
  kind: 'posts' | 'comments',
  id: string,
  body: object = { reason: 'spam' },
) {
  return request(app.getHttpServer())
    .post(`${API}/${kind}/${id}/reports`)
    .set(await as(userId))
    .send(body);
}

/** 글이나 댓글을 지운다. */
async function remove(userId: string, kind: 'posts' | 'comments', id: string) {
  const response = await request(app.getHttpServer())
    .delete(`${API}/${kind}/${id}`)
    .set(await as(userId));
  expect(response.status).toBe(204);
}

/** 운영자의 목록을 읽는다. */
async function openList(userId = OPERATOR, query = '') {
  return request(app.getHttpServer())
    .get(`${API}/reports${query}`)
    .set(await as(userId));
}

/** 글이나 댓글 하나에 걸린 신고를 읽는다. */
async function reportsOf(
  kind: 'posts' | 'comments',
  id: string,
  userId = OPERATOR,
) {
  return request(app.getHttpServer())
    .get(`${API}/${kind}/${id}/reports`)
    .set(await as(userId));
}

/** 글이나 댓글 하나에 걸린 열린 신고를 처리한다. */
async function handle(
  kind: 'posts' | 'comments',
  id: string,
  outcome: unknown = 'actioned',
  userId = OPERATOR,
) {
  return request(app.getHttpServer())
    .put(`${API}/${kind}/${id}/reports/outcome`)
    .set(await as(userId))
    .send({ outcome });
}

describe('POST /posts/:id/reports', () => {
  it('글을 신고하면 201 이고 접수했다는 것만 돌려준다', async () => {
    const postId = await writtenPost();

    const response = await report(READER, 'posts', postId, {
      reason: 'abuse',
      description: '욕설이 있습니다.',
    });

    expect(response.status).toBe(201);
    expect(response.body).toEqual({
      id: '1',
      reason: 'abuse',
      created_at: expect.any(String),
    });
    expect(await readReportRow(app, '1')).toMatchObject({
      post_id: postId,
      comment_id: null,
      reporter_id: READER,
      reason: 'abuse',
      description: '욕설이 있습니다.',
      handled_at: null,
      handled_by: null,
      outcome: null,
    });
  });

  it('설명은 적지 않아도 된다. 적지 않으면 null 이다', async () => {
    const postId = await writtenPost();

    expect((await report(READER, 'posts', postId)).status).toBe(201);
    expect(
      (
        await report(ANOTHER, 'posts', postId, {
          reason: 'spam',
          description: null,
        })
      ).status,
    ).toBe(201);

    expect((await readReportRow(app, '1'))?.description).toBeNull();
    expect((await readReportRow(app, '2'))?.description).toBeNull();
  });

  it('로그인하지 않으면 401 이다', async () => {
    const postId = await writtenPost();

    const response = await request(app.getHttpServer())
      .post(`${API}/posts/${postId}/reports`)
      .send({ reason: 'spam' });

    expect(response.status).toBe(401);
  });

  it('같은 사람이 같은 글을 두 번 신고하면 409 다. 다른 사람은 된다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);

    const again = await report(READER, 'posts', postId, { reason: 'abuse' });

    expect(again.status).toBe(409);
    expect(again.body).toEqual({ detail: '이미 신고했습니다.' });
    expect((await report(ANOTHER, 'posts', postId)).status).toBe(201);
  });

  it('처리해서 닫은 신고가 있어도 같은 사람은 다시 신고하지 못한다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);
    await handle('posts', postId, 'dismissed');

    expect((await report(READER, 'posts', postId)).status).toBe(409);
  });

  it('같은 신고가 동시에 들어와도 하나만 접수한다', async () => {
    const postId = await writtenPost();

    const responses = await Promise.all(
      Array.from({ length: 5 }, () => report(READER, 'posts', postId)),
    );

    const statuses = responses.map((response) => response.status).sort();
    expect(statuses).toEqual([201, 409, 409, 409, 409]);
    const [{ count }] = (await app
      .get(DataSource)
      .query('SELECT count(*)::int AS count FROM "reports"')) as {
      count: number;
    }[];
    expect(count).toBe(1);
  });

  it('자기 글은 신고하지 못한다', async () => {
    const postId = await writtenPost();

    const response = await report(WRITER, 'posts', postId);

    expect(response.status).toBe(403);
    expect(response.body).toEqual({
      detail: '자신의 글은 신고할 수 없습니다.',
    });
  });

  it('지운 글, 없는 글, 번호의 모양이 아닌 것은 404 다', async () => {
    const postId = await writtenPost();
    await remove(WRITER, 'posts', postId);

    for (const id of [postId, '999', 'abc']) {
      const response = await report(READER, 'posts', id);
      expect(response.status).toBe(404);
      expect(response.body).toEqual({ detail: '글을 찾을 수 없습니다.' });
    }
  });

  it.each([
    [{}, 'reason'],
    [{ reason: 'boring' }, 'reason'],
    [{ reason: 'other' }, 'description'],
    [{ reason: 'other', description: '   ' }, 'description'],
    [{ reason: 'spam', description: '' }, 'description'],
    [{ reason: 'spam', description: 3 }, 'description'],
    [{ reason: 'spam', description: 'a\u0000b' }, 'description'],
    [
      { reason: 'spam', description: 'a'.repeat(DESCRIPTION_MAX_LENGTH + 1) },
      'description',
    ],
    [{ reason: 'spam', target: 'x' }, 'target'],
  ])('입력이 틀리면 400 이다: %j', async (body, field) => {
    const postId = await writtenPost();

    const response = await report(READER, 'posts', postId, body);

    expect(response.status).toBe(400);
    expect(Object.keys((response.body as { errors: object }).errors)).toEqual([
      field,
    ]);
  });

  it('기타는 설명을 붙이면 된다. 설명은 정해 둔 길이까지 받는다', async () => {
    const postId = await writtenPost();

    const response = await report(READER, 'posts', postId, {
      reason: 'other',
      description: 'a'.repeat(DESCRIPTION_MAX_LENGTH),
    });

    expect(response.status).toBe(201);
  });

  it('정해 둔 사유는 모두 받는다', async () => {
    const postId = await writtenPost();
    const reporters = [
      READER,
      ANOTHER,
      THIRD,
      OPERATOR,
      '1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e',
    ];

    for (const [index, reason] of REPORT_REASONS.entries()) {
      const response = await report(reporters[index], 'posts', postId, {
        reason,
        description: '설명',
      });
      expect(response.status).toBe(201);
    }
  });
});

describe('POST /comments/:id/reports', () => {
  let postId: string;

  beforeEach(async () => {
    postId = await writtenPost(READER);
  });

  it('댓글과 답글을 신고한다', async () => {
    const commentId = await writtenComment(postId);
    const replyId = await writtenComment(postId, WRITER, commentId);

    expect((await report(READER, 'comments', commentId)).status).toBe(201);
    expect((await report(READER, 'comments', replyId)).status).toBe(201);

    expect(await readReportRow(app, '1')).toMatchObject({
      post_id: null,
      comment_id: commentId,
    });
  });

  it('같은 사람이 글과 그 글의 댓글을 함께 신고할 수 있다', async () => {
    const commentId = await writtenComment(postId);
    const otherPost = await writtenPost(WRITER);

    expect((await report(ANOTHER, 'posts', otherPost)).status).toBe(201);
    expect((await report(ANOTHER, 'comments', commentId)).status).toBe(201);
  });

  it('같은 댓글을 두 번 신고하면 409, 자기 댓글이면 403 이다', async () => {
    const commentId = await writtenComment(postId);
    await report(READER, 'comments', commentId);

    expect((await report(READER, 'comments', commentId)).status).toBe(409);
    const own = await report(WRITER, 'comments', commentId);
    expect(own.status).toBe(403);
    expect(own.body).toEqual({ detail: '자신의 댓글은 신고할 수 없습니다.' });
  });

  it('지운 댓글, 답글이 있어 자리만 남은 댓글, 지운 글의 댓글은 404 다', async () => {
    const deleted = await writtenComment(postId);
    await remove(WRITER, 'comments', deleted);
    const placeholder = await writtenComment(postId);
    await writtenComment(postId, ANOTHER, placeholder);
    await remove(WRITER, 'comments', placeholder);
    const orphan = await writtenComment(postId);
    await remove(READER, 'posts', postId);

    for (const id of [deleted, placeholder, orphan, '999', 'abc']) {
      const response = await report(ANOTHER, 'comments', id);
      expect(response.status).toBe(404);
      expect(response.body).toEqual({ detail: '댓글을 찾을 수 없습니다.' });
    }
  });
});

describe('GET /reports', () => {
  it('운영자가 아니면 403 이다. 로그인하지 않으면 401 이다', async () => {
    const response = await openList(READER);

    expect(response.status).toBe(403);
    expect(response.body).toEqual({
      detail: '운영자만 신고를 볼 수 있습니다.',
    });
    expect(
      (await request(app.getHttpServer()).get(`${API}/reports`)).status,
    ).toBe(401);
  });

  it('신고가 없으면 빈 목록이다', async () => {
    const response = await openList();

    expect(response.status).toBe(200);
    expect(response.body).toEqual({ items: [], page: 1, size: 20, total: 0 });
  });

  it('신고당한 것마다 한 줄로 묶고, 사유마다 센다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId, { reason: 'spam' });
    await report(ANOTHER, 'posts', postId, { reason: 'spam' });
    await report(THIRD, 'posts', postId, {
      reason: 'other',
      description: '설명',
    });

    const response = await openList();

    expect(response.status).toBe(200);
    const body = response.body as Listing<Group>;
    expect(body.total).toBe(1);
    expect(body.items).toEqual([
      {
        target: { type: 'post', id: postId, post_id: postId, deleted: false },
        open_count: 3,
        reasons: { ...NO_REASONS, spam: 2, other: 1 },
        first_reported_at: expect.any(String),
        last_reported_at: expect.any(String),
      },
    ]);
    expect(
      body.items[0].first_reported_at <= body.items[0].last_reported_at,
    ).toBe(true);
  });

  it('글과 댓글은 따로 묶는다. 댓글의 줄은 그 댓글이 달린 글을 알려 준다', async () => {
    const postId = await writtenPost();
    const commentId = await writtenComment(postId);
    await report(READER, 'posts', postId);
    await report(READER, 'comments', commentId, { reason: 'abuse' });

    const body = (await openList()).body as Listing<Group>;

    expect(body.total).toBe(2);
    expect(body.items.map((item) => item.target)).toEqual([
      { type: 'post', id: postId, post_id: postId, deleted: false },
      { type: 'comment', id: commentId, post_id: postId, deleted: false },
    ]);
  });

  it('글의 번호와 댓글의 번호가 같아도 따로 센다', async () => {
    const postId = await writtenPost();
    const commentId = await writtenComment(postId);
    expect(commentId).toBe(postId);
    await report(READER, 'posts', postId);
    await report(READER, 'comments', commentId);

    expect(((await openList()).body as Listing<Group>).total).toBe(2);
  });

  it('처음 신고가 이른 것부터다. 나중에 신고가 더 와도 자리는 그대로다', async () => {
    const first = await writtenPost();
    const second = await writtenPost();
    await report(READER, 'posts', first);
    await report(READER, 'posts', second);
    await report(ANOTHER, 'posts', first);

    const body = (await openList()).body as Listing<Group>;

    expect(body.items.map((item) => item.target.id)).toEqual([first, second]);
  });

  it('쪽으로 나눈다', async () => {
    const ids: string[] = [];
    for (let i = 0; i < 3; i += 1) {
      ids.push(await writtenPost());
      await report(READER, 'posts', ids[i]);
    }

    const body = (await openList(OPERATOR, '?page=2&size=2'))
      .body as Listing<Group>;

    expect(body.total).toBe(3);
    expect(body.page).toBe(2);
    expect(body.items.map((item) => item.target.id)).toEqual([ids[2]]);
  });

  it('신고당한 것을 지워도 신고는 열려 있고, 지웠다는 것을 알려 준다', async () => {
    const postId = await writtenPost();
    const commentId = await writtenComment(postId);
    await report(READER, 'posts', postId);
    await report(READER, 'comments', commentId);
    await remove(OPERATOR, 'comments', commentId);
    await remove(OPERATOR, 'posts', postId);

    const body = (await openList()).body as Listing<Group>;

    expect(body.items.map((item) => item.target.deleted)).toEqual([true, true]);
  });

  it('처리한 신고는 빠진다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);
    await handle('posts', postId);

    expect(((await openList()).body as Listing<Group>).total).toBe(0);
  });
});

describe('GET /posts/:id/reports, GET /comments/:id/reports', () => {
  it('한 글에 걸린 신고를 모두 돌려준다. 최근 것부터고, 설명과 신고한 사람이 나온다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId, {
      reason: 'spam',
      description: '광고',
    });
    await report(ANOTHER, 'posts', postId, { reason: 'abuse' });

    const response = await reportsOf('posts', postId);

    expect(response.status).toBe(200);
    const body = response.body as Listing<ReportItem>;
    expect(body.total).toBe(2);
    expect(body.items).toEqual([
      expect.objectContaining({
        id: '2',
        reason: 'abuse',
        description: null,
        reporter_id: ANOTHER,
        outcome: null,
      }),
      expect.objectContaining({
        id: '1',
        reason: 'spam',
        description: '광고',
        reporter_id: READER,
        outcome: null,
      }),
    ]);
  });

  it('다른 글과 댓글의 신고는 섞이지 않는다', async () => {
    const postId = await writtenPost();
    const otherPost = await writtenPost();
    const commentId = await writtenComment(postId);
    await report(READER, 'posts', postId);
    await report(READER, 'posts', otherPost);
    await report(READER, 'comments', commentId);

    const forPost = (await reportsOf('posts', postId))
      .body as Listing<ReportItem>;
    const forComment = (await reportsOf('comments', commentId))
      .body as Listing<ReportItem>;

    expect(forPost.items.map((item) => item.id)).toEqual(['1']);
    expect(forComment.items.map((item) => item.id)).toEqual(['3']);
  });

  it('지운 글의 신고도 읽는다. 신고가 없으면 빈 목록이다', async () => {
    const postId = await writtenPost();
    const quiet = await writtenPost();
    await report(READER, 'posts', postId);
    await remove(WRITER, 'posts', postId);

    expect(
      ((await reportsOf('posts', postId)).body as Listing<ReportItem>).total,
    ).toBe(1);
    expect((await reportsOf('posts', quiet)).body).toEqual({
      items: [],
      page: 1,
      size: 20,
      total: 0,
    });
  });

  it('운영자가 아니면 403 이다. 글쓴이도 누가 신고했는지 보지 못한다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);

    expect((await reportsOf('posts', postId, WRITER)).status).toBe(403);
    expect((await reportsOf('posts', postId, READER)).status).toBe(403);
  });

  it('운영자가 아니면 없는 글이어도 403 이다. 운영자에게는 404 다', async () => {
    expect((await reportsOf('posts', '999', READER)).status).toBe(403);
    expect((await reportsOf('posts', '999')).status).toBe(404);
    expect((await reportsOf('comments', '999')).status).toBe(404);
  });
});

describe('PUT /posts/:id/reports/outcome, PUT /comments/:id/reports/outcome', () => {
  it('열린 신고를 모두 한 번에 닫는다. 처리한 운영자와 결과가 남는다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);
    await report(ANOTHER, 'posts', postId);

    const response = await handle('posts', postId, 'actioned');

    expect(response.status).toBe(204);
    const items = (
      (await reportsOf('posts', postId)).body as Listing<ReportItem>
    ).items;
    expect(items).toHaveLength(2);
    for (const item of items) {
      expect(item).toMatchObject({
        handled_by: OPERATOR,
        outcome: 'actioned',
        handled_at: expect.any(String),
      });
    }
    // 한 문장으로 닫으므로 처리한 시각이 같다
    expect(items[0].handled_at).toBe(items[1].handled_at);
  });

  it('닫은 뒤에 새 신고가 오면 다시 열린다. 앞의 처리는 그대로다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);
    await handle('posts', postId, 'dismissed');

    await report(ANOTHER, 'posts', postId);

    const group = ((await openList()).body as Listing<Group>).items[0];
    expect(group.open_count).toBe(1);
    expect(await readReportRow(app, '1')).toMatchObject({
      outcome: 'dismissed',
    });
    expect(await readReportRow(app, '2')).toMatchObject({ outcome: null });
  });

  it('열린 신고가 없으면 404 다. 두 번 처리하면 두 번째가 404 다', async () => {
    const postId = await writtenPost();
    expect((await handle('posts', postId)).status).toBe(404);

    await report(READER, 'posts', postId);
    expect((await handle('posts', postId)).status).toBe(204);

    const again = await handle('posts', postId);
    expect(again.status).toBe(404);
    expect(again.body).toEqual({ detail: '처리할 신고가 없습니다.' });
  });

  it('댓글의 신고를 닫아도 그 글의 신고는 열려 있다', async () => {
    const postId = await writtenPost();
    const commentId = await writtenComment(postId);
    await report(READER, 'posts', postId);
    await report(READER, 'comments', commentId);

    expect((await handle('comments', commentId)).status).toBe(204);

    const body = (await openList()).body as Listing<Group>;
    expect(body.items.map((item) => item.target.type)).toEqual(['post']);
  });

  it('지운 글의 신고도 처리한다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);
    await remove(OPERATOR, 'posts', postId);

    expect((await handle('posts', postId)).status).toBe(204);
  });

  it('운영자가 아니면 403 이고 닫지 않는다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);

    expect((await handle('posts', postId, 'dismissed', WRITER)).status).toBe(
      403,
    );
    expect(((await openList()).body as Listing<Group>).total).toBe(1);
  });

  it.each([{}, { outcome: 'deleted' }, { outcome: 3 }])(
    '결과가 틀리면 400 이다: %j',
    async (body) => {
      const postId = await writtenPost();
      await report(READER, 'posts', postId);

      const response = await request(app.getHttpServer())
        .put(`${API}/posts/${postId}/reports/outcome`)
        .set(await as(OPERATOR))
        .send(body);

      expect(response.status).toBe(400);
    },
  );

  it('없는 글과 댓글은 404 다', async () => {
    expect((await handle('posts', '999')).status).toBe(404);
    expect((await handle('comments', '999')).status).toBe(404);
    expect((await handle('posts', 'abc')).status).toBe(404);
  });
});

describe('DB 가 지키는 약속', () => {
  it('글도 댓글도 가리키지 않거나 둘 다 가리키는 신고는 넣을 수 없다', async () => {
    const postId = await writtenPost();
    const commentId = await writtenComment(postId);
    const db = app.get(DataSource);
    const insert = (post: string | null, comment: string | null) =>
      db.query(
        `INSERT INTO "reports" ("post_id", "comment_id", "reporter_id", "reason") VALUES ($1, $2, $3, 'spam')`,
        [post, comment, READER],
      );

    await expect(insert(null, null)).rejects.toThrow(/ck_reports_one_target/);
    await expect(insert(postId, commentId)).rejects.toThrow(
      /ck_reports_one_target/,
    );
  });

  it('처리한 시각, 처리한 사람, 결과는 함께 있어야 한다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);

    await expect(
      app.get(DataSource).query(`UPDATE "reports" SET "outcome" = 'actioned'`),
    ).rejects.toThrow(/ck_reports_handled_together/);
  });

  it('신고가 걸린 글의 행은 지울 수 없다', async () => {
    const postId = await writtenPost();
    await report(READER, 'posts', postId);

    await expect(
      app
        .get(DataSource)
        .query(`DELETE FROM "posts" WHERE "id" = $1`, [postId]),
    ).rejects.toThrow(/fk_reports_post/);
  });
});
