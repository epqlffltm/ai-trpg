// board-server/test/authors.e2e-spec.ts

/**
 * 글쓴이의 닉네임을 앱을 통째로 만들어 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 *
 * 닉네임은 access 토큰에 실려 온다(인증 서버의 nickname 클레임). 로그인한 요청마다 적어 두고,
 * 글과 댓글의 응답에 author_nickname 으로 싣는다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { DataSource } from 'typeorm';
import { API_PREFIX } from '../src/app.setup.js';
import { createTestApp, useKeys } from './app.js';
import { clearData, makeOperator, readAuthorRow } from './data.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;

/** 테스트에 나오는 사람들. 인증 서버의 public_id 다 */
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const READER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const OPERATOR = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';

/** 글과 댓글의 응답에서 테스트가 읽는 칸. */
interface Authored {
  id: string;
  author_id: string | null;
  author_nickname: string | null;
}

/** 댓글 목록의 한 줄. */
interface Thread extends Authored {
  replies: Authored[];
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
});

/** 이 사람의 토큰을 붙인 머리말. nickname 을 주지 않으면 이름이 없는 토큰이다. */
async function as(
  userId: string,
  nickname?: string,
): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId, nickname })}`,
  };
}

/** 글을 쓴다. */
async function write(userId: string, nickname?: string, board = 'free') {
  return request(app.getHttpServer())
    .post(`${API}/boards/${board}/posts`)
    .set(await as(userId, nickname))
    .send({ title: '글', content: '본문입니다.' });
}

/** 글을 써서 그 번호를 돌려준다. */
async function writtenId(userId: string, nickname?: string): Promise<string> {
  const response = await write(userId, nickname);
  expect(response.status).toBe(201);
  return (response.body as Authored).id;
}

/** 댓글을 단다. parentId 를 주면 답글이다. */
async function comment(
  postId: string,
  userId: string,
  nickname?: string,
  parentId?: string,
) {
  return request(app.getHttpServer())
    .post(`${API}/posts/${postId}/comments`)
    .set(await as(userId, nickname))
    .send({ content: '댓글입니다.', parent_id: parentId });
}

/** 로그인한 채로 게시판을 연다. 화면이 처음에 부르는 것과 같다. */
async function visit(userId: string, nickname?: string): Promise<void> {
  const response = await request(app.getHttpServer())
    .get(`${API}/me`)
    .set(await as(userId, nickname));
  expect(response.status).toBe(200);
}

/** 글 하나를 로그인 없이 읽는다. */
async function read(postId: string): Promise<Authored> {
  const response = await request(app.getHttpServer()).get(
    `${API}/posts/${postId}`,
  );
  return response.body as Authored;
}

/** 자유 게시판의 글 목록을 로그인 없이 읽는다. */
async function listed(): Promise<Authored[]> {
  const response = await request(app.getHttpServer()).get(
    `${API}/boards/free/posts`,
  );
  return (response.body as { items: Authored[] }).items;
}

/** 한 글의 댓글 목록을 로그인 없이 읽는다. */
async function threads(postId: string): Promise<Thread[]> {
  const response = await request(app.getHttpServer()).get(
    `${API}/posts/${postId}/comments`,
  );
  return (response.body as { items: Thread[] }).items;
}

describe('글쓴이의 닉네임을 싣는다', () => {
  it('글을 쓴 응답에 바로 나오고, 적어 둔다', async () => {
    const response = await write(WRITER, '모험가');

    expect(response.status).toBe(201);
    expect(response.body).toMatchObject({
      author_id: WRITER,
      author_nickname: '모험가',
    });
    expect(await readAuthorRow(app, WRITER)).toMatchObject({
      nickname: '모험가',
    });
  });

  it('글 읽기, 글 목록, 고정한 글, 검색에도 나온다', async () => {
    await makeOperator(app, OPERATOR);
    const mine = await writtenId(WRITER, '모험가');
    const pinnedId = await writtenId(READER, '구경꾼');
    await request(app.getHttpServer())
      .put(`${API}/posts/${pinnedId}/pin`)
      .set(await as(OPERATOR, '운영자'));

    expect((await read(mine)).author_nickname).toBe('모험가');
    const board = await request(app.getHttpServer()).get(
      `${API}/boards/free/posts`,
    );
    const body = board.body as { pinned: Authored[]; items: Authored[] };
    expect(body.pinned.map((post) => post.author_nickname)).toEqual(['구경꾼']);
    expect(body.items.map((post) => post.author_nickname)).toEqual(['모험가']);
    const found = await request(app.getHttpServer())
      .get(`${API}/posts`)
      .query({ q: '본문' });
    expect(
      (found.body as { items: Authored[] }).items.map(
        (post) => post.author_nickname,
      ),
    ).toEqual(['구경꾼', '모험가']);
  });

  it('댓글과 답글에도 나온다. 쓴 응답에도, 목록에도', async () => {
    const postId = await writtenId(WRITER, '모험가');

    const written = await comment(postId, READER, '구경꾼');
    const parent = (written.body as Authored).id;
    const reply = await comment(postId, WRITER, '모험가', parent);

    expect(written.body).toMatchObject({ author_nickname: '구경꾼' });
    expect(reply.body).toMatchObject({ author_nickname: '모험가' });
    const [thread] = await threads(postId);
    expect(thread.author_nickname).toBe('구경꾼');
    expect(thread.replies.map((item) => item.author_nickname)).toEqual([
      '모험가',
    ]);
  });

  it('지운 댓글의 자리에는 이름도 나오지 않는다', async () => {
    const postId = await writtenId(WRITER, '모험가');
    const parent = ((await comment(postId, READER, '구경꾼')).body as Authored)
      .id;
    await comment(postId, WRITER, '모험가', parent);
    await request(app.getHttpServer())
      .delete(`${API}/comments/${parent}`)
      .set(await as(READER, '구경꾼'));

    const [thread] = await threads(postId);

    expect(thread).toMatchObject({ author_id: null, author_nickname: null });
  });
});

describe('닉네임이 바뀌면', () => {
  it('새 이름으로 글을 쓰면 예전 글에도 새 이름이 나온다', async () => {
    const old = await writtenId(WRITER, '모험가');

    await write(WRITER, '용사');

    expect((await read(old)).author_nickname).toBe('용사');
    expect((await listed()).map((post) => post.author_nickname)).toEqual([
      '용사',
      '용사',
    ]);
  });

  it('글을 쓰지 않아도, 로그인한 채로 들어오기만 하면 새 이름이 나온다', async () => {
    const old = await writtenId(WRITER, '모험가');

    await visit(WRITER, '용사');

    expect((await read(old)).author_nickname).toBe('용사');
  });

  it('로그인 없이 부르는 주소는 토큰을 보지 않으므로 이름도 받지 않는다', async () => {
    const old = await writtenId(WRITER, '모험가');

    await request(app.getHttpServer())
      .get(`${API}/posts/${old}`)
      .set(await as(WRITER, '용사'));

    expect((await read(old)).author_nickname).toBe('모험가');
  });

  it('다른 사람의 이름은 건드리지 않는다', async () => {
    const theirs = await writtenId(READER, '구경꾼');

    await visit(WRITER, '모험가');

    expect((await read(theirs)).author_nickname).toBe('구경꾼');
  });

  it('DB 의 이름과 같으면 행을 고치지 않는다', async () => {
    await app
      .get(DataSource)
      .query(
        `INSERT INTO "authors" ("user_id", "nickname", "updated_at") VALUES ($1, '모험가', '2026-01-01T00:00:00Z')`,
        [WRITER],
      );

    await visit(WRITER, '모험가');

    const row = await readAuthorRow(app, WRITER);
    expect((row?.updated_at as Date).toISOString()).toBe(
      '2026-01-01T00:00:00.000Z',
    );
  });

  it('이름이 다르면 고치고 고친 시각을 적는다', async () => {
    await app
      .get(DataSource)
      .query(
        `INSERT INTO "authors" ("user_id", "nickname", "updated_at") VALUES ($1, '모험가', '2026-01-01T00:00:00Z')`,
        [WRITER],
      );

    await visit(WRITER, '용사');

    const row = await readAuthorRow(app, WRITER);
    expect(row?.nickname).toBe('용사');
    expect((row?.updated_at as Date).getTime()).toBeGreaterThan(
      Date.parse('2026-01-01T00:00:00Z'),
    );
  });
});

describe('닉네임을 모를 때', () => {
  it('이름이 없는 토큰으로 쓴 글은 null 이다. 토큰은 그대로 받는다', async () => {
    const response = await write(WRITER);

    expect(response.status).toBe(201);
    expect(response.body).toMatchObject({ author_nickname: null });
    expect(await readAuthorRow(app, WRITER)).toBeUndefined();
  });

  it('이름이 없는 토큰이 와도 적어 둔 이름은 지우지 않는다', async () => {
    const postId = await writtenId(WRITER, '모험가');

    await visit(WRITER);

    expect((await read(postId)).author_nickname).toBe('모험가');
  });

  it('나중에 이름이 실린 토큰이 오면 예전 글에도 이름이 나온다', async () => {
    const postId = await writtenId(WRITER);

    await visit(WRITER, '모험가');

    expect((await read(postId)).author_nickname).toBe('모험가');
  });

  it.each([
    ['줄바꿈', '모험\n가'],
    ['보이지 않는 글자', 'a​b'],
    ['너무 긴 것', 'a'.repeat(51)],
  ])(
    '받아들일 수 없는 이름(%s)은 적지 않는다. 토큰은 받는다',
    async (_, nickname) => {
      const response = await write(WRITER, nickname);

      expect(response.status).toBe(201);
      expect(response.body).toMatchObject({ author_nickname: null });
      expect(await readAuthorRow(app, WRITER)).toBeUndefined();
    },
  );
});
