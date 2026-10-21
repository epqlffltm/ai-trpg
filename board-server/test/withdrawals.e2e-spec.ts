// board-server/test/withdrawals.e2e-spec.ts

/**
 * 인증 서버가 탈퇴를 알리는 API(src/withdrawals/)를 앱을 통째로 만들어 본다(#603). 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 *
 * 보는 것.
 *   - 정리: 그 사람의 글과 댓글(지운 것도)의 글쓴이를 비운다. 글과 댓글은 남는다. 신고한 사람을 비운다.
 *     닉네임과 그 사람에게 보낼 알림을 지운다. 다른 사람의 것은 그대로다
 *   - 보이는 것: 응답의 author_id 와 author_nickname 이 null 이고 author_withdrawn 이 true 다
 *   - 그 뒤: 탈퇴한 사람의 글에 댓글을 달아도 알림이 없다. 운영자는 지울 수 있다. 누구나 신고할 수 있다
 *   - 몇 번을 받아도, 모르는 사람이어도 200 processed 다
 *   - 인증 서버의 서명이 아니면 401, 본문과 주소가 틀리면 400 이다. 어느 쪽이든 아무것도 바꾸지 않는다
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { DataSource } from 'typeorm';
import { API_PREFIX } from '../src/app.setup.js';
import { OutgoingNotification } from '../src/notifications/outgoing-notification.entity.js';
import { SIGNATURE_HEADER, sign } from '../src/service-auth/signing.js';
import { createTestApp, useKeys } from './app.js';
import {
  clearData,
  makeOperator,
  readAuthorRow,
  readCommentRow,
  readPostRow,
  readReportRow,
} from './data.js';
import { TEST_AUTH_SERVER_SECRET } from './setup.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;

const LEAVING = '6f1e2d3c-4b5a-4c6d-8e7f-0a1b2c3d4e5f';
const STAYING = '1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d';
const OPERATOR = '9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b';
/** 인증 서버가 보내는 본문(auth-server/accounts/withdrawal_client.py 의 isoformat) */
const BODY = '{"withdrawn_at": "2026-10-28T03:00:00.123456+00:00"}';

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
});

async function as(
  userId: string,
  nickname?: string,
): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId, nickname })}`,
  };
}

/** 그 사람이 자유 게시판에 글을 써서 그 번호를 돌려준다. 닉네임이 적힌다. */
async function writePost(userId: string): Promise<string> {
  const response = await request(app.getHttpServer())
    .post(`${API}/boards/free/posts`)
    .set(await as(userId, `이름${userId.slice(0, 4)}`))
    .send({ title: '첫 모험', content: '본문입니다.' });
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 그 사람이 글에 댓글을 달아 그 번호를 돌려준다. parentId 를 주면 답글이다. */
async function writeComment(
  userId: string,
  postId: string,
  parentId?: string,
): Promise<string> {
  const response = await request(app.getHttpServer())
    .post(`${API}/posts/${postId}/comments`)
    .set(await as(userId))
    .send({ content: '댓글입니다.', parent_id: parentId });
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 그 사람이 글을 신고한다. 응답을 그대로 돌려준다. */
async function reportPost(
  userId: string,
  postId: string,
): Promise<request.Response> {
  return request(app.getHttpServer())
    .post(`${API}/posts/${postId}/reports`)
    .set(await as(userId))
    .send({ reason: 'spam' });
}

/** 인증 서버처럼 서명해 그 사람의 탈퇴를 알린다. secret 과 signedPath 로 한 가지씩 틀리게 바꾼다. */
function withdraw(
  userId: string,
  options: { body?: string; secret?: string; signedPath?: string } = {},
): request.Test {
  const path = `${API}/service/users/${userId}/withdrawal`;
  const body = options.body ?? BODY;
  const signature = sign(
    options.secret ?? TEST_AUTH_SERVER_SECRET,
    Math.floor(Date.now() / 1000),
    'POST',
    options.signedPath ?? path,
    body,
  );
  return request(app.getHttpServer())
    .post(path)
    .set(SIGNATURE_HEADER, signature)
    .set('Content-Type', 'application/json')
    .send(body);
}

/** 발송함의 모든 줄의 받는 사람. */
async function outgoingUsers(): Promise<string[]> {
  const rows = await app
    .get(DataSource)
    .getRepository(OutgoingNotification)
    .find({ order: { id: 'ASC' } });
  return rows.map((row) => row.userId);
}

describe('정리', () => {
  it('글과 댓글은 남기고 글쓴이만 비운다. 고친 시각은 그대로다', async () => {
    const postId = await writePost(LEAVING);
    const commentId = await writeComment(LEAVING, postId);
    const before = await readPostRow(app, postId);

    const response = await withdraw(LEAVING);

    expect(response.status).toBe(200);
    expect(response.body).toEqual({ status: 'processed' });
    const post = await readPostRow(app, postId);
    expect([post?.author_id, post?.title, post?.content]).toEqual([
      null,
      '첫 모험',
      '본문입니다.',
    ]);
    expect(post?.updated_at).toEqual(before?.updated_at);
    expect((await readCommentRow(app, commentId))?.author_id).toBeNull();
  });

  it('지운 글과 댓글의 글쓴이도 비운다', async () => {
    const postId = await writePost(LEAVING);
    const commentId = await writeComment(LEAVING, postId);
    await request(app.getHttpServer())
      .delete(`${API}/comments/${commentId}`)
      .set(await as(LEAVING))
      .expect(204);
    await request(app.getHttpServer())
      .delete(`${API}/posts/${postId}`)
      .set(await as(LEAVING))
      .expect(204);

    await withdraw(LEAVING).expect(200);

    expect((await readPostRow(app, postId))?.author_id).toBeNull();
    expect((await readCommentRow(app, commentId))?.author_id).toBeNull();
  });

  it('신고는 남기고 신고한 사람만 비운다', async () => {
    const postId = await writePost(STAYING);
    const report = await reportPost(LEAVING, postId);
    expect(report.status).toBe(201);
    const reportId = (report.body as { id: string }).id;

    await withdraw(LEAVING).expect(200);

    const row = await readReportRow(app, reportId);
    expect([row?.reporter_id, row?.reason]).toEqual([null, 'spam']);
  });

  it('닉네임과 그 사람에게 보낼 알림을 지운다', async () => {
    const postId = await writePost(LEAVING);
    await writeComment(STAYING, postId);
    expect(await outgoingUsers()).toEqual([LEAVING]);

    await withdraw(LEAVING).expect(200);

    expect(await readAuthorRow(app, LEAVING)).toBeUndefined();
    expect(await outgoingUsers()).toEqual([]);
  });

  it('다른 사람의 것은 그대로다', async () => {
    const mine = await writePost(STAYING);
    const theirs = await writePost(LEAVING);
    await writeComment(LEAVING, mine);

    await withdraw(LEAVING).expect(200);

    expect((await readPostRow(app, mine))?.author_id).toBe(STAYING);
    expect(await readAuthorRow(app, STAYING)).toBeDefined();
    expect(await outgoingUsers()).toEqual([STAYING]);
    expect((await readPostRow(app, theirs))?.author_id).toBeNull();
  });
});

describe('보이는 것', () => {
  it('글은 "탈퇴한 사용자"의 글로 보인다', async () => {
    const postId = await writePost(LEAVING);
    await withdraw(LEAVING).expect(200);

    const post = await request(app.getHttpServer())
      .get(`${API}/posts/${postId}`)
      .expect(200);
    const list = await request(app.getHttpServer())
      .get(`${API}/boards/free/posts`)
      .expect(200);

    const shown = post.body as Record<string, unknown>;
    expect([
      shown.author_id,
      shown.author_nickname,
      shown.author_withdrawn,
    ]).toEqual([null, null, true]);
    const [item] = (list.body as { items: Record<string, unknown>[] }).items;
    expect([item.author_id, item.author_withdrawn]).toEqual([null, true]);
  });

  it('댓글도 같다. 다른 사람의 댓글은 author_withdrawn 이 false 다', async () => {
    const postId = await writePost(STAYING);
    await writeComment(LEAVING, postId);
    await writeComment(STAYING, postId);
    await withdraw(LEAVING).expect(200);

    const response = await request(app.getHttpServer())
      .get(`${API}/posts/${postId}/comments`)
      .expect(200);

    const items = (response.body as { items: Record<string, unknown>[] }).items;
    expect(
      items.map((item) => [
        item.author_id,
        item.author_nickname,
        item.author_withdrawn,
      ]),
    ).toEqual([
      [null, null, true],
      [STAYING, expect.any(String), false],
    ]);
  });
});

describe('그 뒤', () => {
  it('탈퇴한 사람의 글과 댓글에 달린 것은 알리지 않는다', async () => {
    const postId = await writePost(LEAVING);
    const commentId = await writeComment(LEAVING, postId);
    await withdraw(LEAVING).expect(200);

    await writeComment(STAYING, postId);
    await writeComment(STAYING, postId, commentId);

    expect(await outgoingUsers()).toEqual([]);
  });

  it('운영자는 탈퇴한 사람의 글을 지운다', async () => {
    makeOperator(OPERATOR);
    const postId = await writePost(LEAVING);
    await withdraw(LEAVING).expect(200);

    await request(app.getHttpServer())
      .delete(`${API}/posts/${postId}`)
      .set(await as(OPERATOR))
      .expect(204);
  });

  it('누구나 탈퇴한 사람의 글을 신고한다', async () => {
    const postId = await writePost(LEAVING);
    await withdraw(LEAVING).expect(200);

    expect((await reportPost(STAYING, postId)).status).toBe(201);
  });
});

describe('다시 받기', () => {
  it('같은 알림을 다시 받아도 200 processed 다', async () => {
    await writePost(LEAVING);
    await withdraw(LEAVING).expect(200);

    const again = await withdraw(LEAVING);

    expect([again.status, again.body]).toEqual([200, { status: 'processed' }]);
  });

  it('이 서버가 모르는 사람도 200 processed 다', async () => {
    const response = await withdraw('2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e');

    expect([response.status, response.body]).toEqual([
      200,
      { status: 'processed' },
    ]);
  });
});

describe('서명과 입력', () => {
  it.each([
    ['다른 비밀', { secret: 'board-someone-else-secret-0123456789' }],
    [
      '다른 주소의 서명',
      { signedPath: `${API}/service/users/${STAYING}/withdrawal` },
    ],
  ])('%s 이면 401 이고 아무것도 바꾸지 않는다', async (_, options) => {
    const postId = await writePost(LEAVING);

    const response = await withdraw(LEAVING, options);

    expect(response.status).toBe(401);
    expect((await readPostRow(app, postId))?.author_id).toBe(LEAVING);
  });

  it('쿼리까지 서명한다. 쿼리를 빼고 한 서명은 받지 않는다', async () => {
    const path = `${API}/service/users/${LEAVING}/withdrawal`;
    const signedWithout = sign(
      TEST_AUTH_SERVER_SECRET,
      Math.floor(Date.now() / 1000),
      'POST',
      path,
      BODY,
    );

    const response = await request(app.getHttpServer())
      .post(`${path}?retry=1`)
      .set(SIGNATURE_HEADER, signedWithout)
      .set('Content-Type', 'application/json')
      .send(BODY);

    expect(response.status).toBe(401);
  });

  it('서명 없이 사용자의 토큰으로는 부를 수 없다', async () => {
    const postId = await writePost(LEAVING);

    const response = await request(app.getHttpServer())
      .post(`${API}/service/users/${LEAVING}/withdrawal`)
      .set(await as(LEAVING))
      .set('Content-Type', 'application/json')
      .send(BODY);

    expect(response.status).toBe(401);
    expect((await readPostRow(app, postId))?.author_id).toBe(LEAVING);
  });

  it.each([
    ['빠진 시각', '{}'],
    ['시간대가 없는 시각', '{"withdrawn_at": "2026-10-28T03:00:00"}'],
    ['시각이 아닌 값', '{"withdrawn_at": "어제"}'],
    ['모르는 칸', `{"withdrawn_at": "2026-10-28T03:00:00Z", "email": "a@b.c"}`],
  ])('%s 이면 400 이고 아무것도 바꾸지 않는다', async (_, body) => {
    const postId = await writePost(LEAVING);

    const response = await withdraw(LEAVING, { body });

    expect(response.status).toBe(400);
    expect((await readPostRow(app, postId))?.author_id).toBe(LEAVING);
  });

  it('주소의 번호가 UUID 가 아니면 400 이다', async () => {
    const response = await withdraw('not-a-uuid');

    expect(response.status).toBe(400);
  });
});
