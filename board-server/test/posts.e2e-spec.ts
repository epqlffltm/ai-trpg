// board-server/test/posts.e2e-spec.ts

/**
 * 글의 API 를 앱을 통째로 만들어 불러 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 * 인증 서버는 띄우지 않는다. 테스트가 만든 키로 사용자마다 토큰을 서명한다.
 *
 * 테스트마다 글과 운영자를 비우고 시작한다. 게시판은 마이그레이션이 넣은 넷을 쓴다.
 * notice 는 운영자만 쓰고, free 는 로그인한 누구나 쓴다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { createTestApp, useKeys } from './app.js';
import { clearData, makeOperator, readPostRow } from './data.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;

/** 테스트에 나오는 사람들. 인증 서버의 public_id 다 */
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const STRANGER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const OPERATOR = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';

const POST = { title: '첫 글', content: '본문입니다.' };

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

/** 이 사람의 토큰을 붙인 머리말. */
async function as(userId: string): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId })}`,
  };
}

/** 게시판에 글을 쓴다. */
async function write(
  userId: string,
  board = 'free',
  body: object = POST,
): Promise<request.Response> {
  return request(app.getHttpServer())
    .post(`${API}/boards/${board}/posts`)
    .set(await as(userId))
    .send(body);
}

/** 글을 써서 그 번호를 돌려준다. 준비 단계에서 쓴다. */
async function writtenId(userId: string, board = 'free', title = POST.title) {
  const response = await write(userId, board, { ...POST, title });
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 글을 읽는다. 로그인하지 않는다. */
function read(id: string): request.Test {
  return request(app.getHttpServer()).get(`${API}/posts/${id}`);
}

/** 글 목록을 읽는다. 로그인하지 않는다. */
function list(board = 'free', query = ''): request.Test {
  return request(app.getHttpServer()).get(
    `${API}/boards/${board}/posts${query}`,
  );
}

describe('글 쓰기', () => {
  it('로그인한 사람이 쓰면 201 과 쓴 글을 돌려준다', async () => {
    const response = await write(WRITER);

    expect(response.status).toBe(201);
    expect(response.body).toEqual({
      id: '1',
      board: 'free',
      author_id: WRITER,
      title: '첫 글',
      comment_count: 0,
      content: '본문입니다.',
      created_at: expect.any(String),
      updated_at: expect.any(String),
    });
    expect(response.body.updated_at).toBe(response.body.created_at);
  });

  it('글 번호는 차례대로 매겨지고 글자로 온다', async () => {
    const first = await writtenId(WRITER);
    const second = await writtenId(WRITER, 'scenario');

    // 게시판마다 따로 세지 않는다
    expect([first, second]).toEqual(['1', '2']);
  });

  it('글쓴이는 토큰의 주인이다. 본문으로 정할 수 없다', async () => {
    const response = await write(WRITER, 'free', {
      ...POST,
      author_id: STRANGER,
    });

    expect(response.status).toBe(400);
    expect(response.body.errors).toHaveProperty('author_id');
  });

  it('로그인하지 않으면 401 이다', async () => {
    const response = await request(app.getHttpServer())
      .post(`${API}/boards/free/posts`)
      .send(POST);

    expect(response.status).toBe(401);
    expect(response.body).toEqual({ detail: '인증이 필요합니다.' });
  });

  it('없는 게시판이면 404 다', async () => {
    const response = await write(WRITER, 'no-such-board');

    expect(response.status).toBe(404);
    expect(response.body).toEqual({ detail: '게시판을 찾을 수 없습니다.' });
  });

  it('입력이 틀리면 400 이고 저장하지 않는다', async () => {
    const response = await write(WRITER, 'free', { title: '', content: '' });

    expect(response.status).toBe(400);
    expect(Object.keys(response.body.errors)).toEqual(['title', 'content']);
    expect((await list()).body.total).toBe(0);
  });

  it('제목의 앞뒤 빈칸은 떼고, 본문은 그대로 저장한다', async () => {
    const content = '  들여쓴 첫 줄\n\n<script>alert(1)</script>\n';

    const response = await write(WRITER, 'free', {
      title: '  제목  ',
      content,
    });

    // 서버는 HTML 로 해석하지도 지우지도 않는다. 받은 글자 그대로다
    expect(response.body).toMatchObject({ title: '제목', content });
  });

  it('운영자만 쓰는 게시판에 운영자가 아닌 사람이 쓰면 403 이다', async () => {
    const response = await write(WRITER, 'notice');

    expect(response.status).toBe(403);
    expect(response.body).toEqual({
      detail: '이 게시판에는 운영자만 글을 쓸 수 있습니다.',
    });
    expect((await list('notice')).body.total).toBe(0);
  });

  it('운영자만 쓰는 게시판에 운영자는 쓴다', async () => {
    await makeOperator(app, OPERATOR);

    const response = await write(OPERATOR, 'notice');

    expect(response.status).toBe(201);
    expect(response.body).toMatchObject({
      board: 'notice',
      author_id: OPERATOR,
    });
  });
});

describe('글 읽기', () => {
  it('로그인 없이 글 하나를 본문까지 돌려준다', async () => {
    const id = await writtenId(WRITER);

    const response = await read(id);

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({
      id,
      board: 'free',
      author_id: WRITER,
      title: '첫 글',
      content: '본문입니다.',
    });
  });

  it('없는 글이면 404 다', async () => {
    const response = await read('999');

    expect(response.status).toBe(404);
    expect(response.body).toEqual({ detail: '글을 찾을 수 없습니다.' });
  });

  it.each(['abc', '0', '-1', '1.5', '99999999999999999999999'])(
    '글 번호의 모양이 아니면(%s) 404 다',
    async (id) => {
      const response = await read(id);

      // DB 까지 가지 않는다. 숫자가 아닌 값을 bigint 칸에 물으면 DB 가 오류를 낸다
      expect(response.status).toBe(404);
    },
  );
});

describe('글 목록', () => {
  it('로그인 없이 새 글부터 돌려주고, 본문은 싣지 않는다', async () => {
    await writtenId(WRITER, 'free', '먼저 쓴 글');
    await writtenId(STRANGER, 'free', '나중에 쓴 글');

    const response = await list();

    expect(response.status).toBe(200);
    expect(response.body).toEqual({
      items: [
        {
          id: '2',
          board: 'free',
          author_id: STRANGER,
          title: '나중에 쓴 글',
          comment_count: 0,
          created_at: expect.any(String),
          updated_at: expect.any(String),
        },
        {
          id: '1',
          board: 'free',
          author_id: WRITER,
          title: '먼저 쓴 글',
          comment_count: 0,
          created_at: expect.any(String),
          updated_at: expect.any(String),
        },
      ],
      page: 1,
      size: 20,
      total: 2,
    });
  });

  it('글이 없으면 빈 목록이다', async () => {
    const response = await list();

    expect(response.body).toEqual({ items: [], page: 1, size: 20, total: 0 });
  });

  it('그 게시판의 글만 돌려준다', async () => {
    await writtenId(WRITER, 'free', '자유');
    await writtenId(WRITER, 'scenario', '시나리오');

    const response = await list('scenario');

    expect(response.body.total).toBe(1);
    expect(response.body.items[0].title).toBe('시나리오');
  });

  it('쪽으로 나눠 돌려준다', async () => {
    for (let number = 1; number <= 5; number += 1) {
      await writtenId(WRITER, 'free', `글 ${number}`);
    }
    const titles = (response: request.Response): string[] =>
      (response.body.items as { title: string }[]).map((item) => item.title);

    const first = await list('free', '?page=1&size=2');
    const second = await list('free', '?page=2&size=2');
    const third = await list('free', '?page=3&size=2');
    const beyond = await list('free', '?page=4&size=2');

    expect(titles(first)).toEqual(['글 5', '글 4']);
    expect(titles(second)).toEqual(['글 3', '글 2']);
    expect(titles(third)).toEqual(['글 1']);
    // 끝을 넘은 쪽은 오류가 아니라 빈 목록이다. 전체 개수는 그대로 알려 준다
    expect(beyond.body).toEqual({ items: [], page: 4, size: 2, total: 5 });
    expect(second.body).toMatchObject({ page: 2, size: 2, total: 5 });
  });

  it('번호가 열 자리를 넘어가도 큰 번호가 먼저다', async () => {
    // 글자로 줄 세우면 '9' 가 '10' 보다 앞에 온다. 숫자로 줄 세우는지 본다
    for (let number = 1; number <= 11; number += 1) {
      await writtenId(WRITER, 'free', `글 ${number}`);
    }

    const response = await list('free', '?size=3');

    expect(
      (response.body.items as { id: string }[]).map((item) => item.id),
    ).toEqual(['11', '10', '9']);
  });

  it.each(['?page=0', '?page=abc', '?size=0', '?size=51', '?size=all'])(
    '쪽이나 크기가 틀리면(%s) 400 이다',
    async (query) => {
      const response = await list('free', query);

      expect(response.status).toBe(400);
      expect(response.body.detail).toBe('입력이 올바르지 않습니다.');
    },
  );

  it('없는 게시판이면 404 다', async () => {
    const response = await list('no-such-board');

    expect(response.status).toBe(404);
  });

  it.each(['%00', 'FREE', "free'--", 'a'.repeat(31)])(
    '게시판 이름의 모양이 아니면(%s) 404 다',
    async (board) => {
      const response = await list(board);

      // DB 까지 가지 않는다. NUL 글자를 DB 에 물으면 DB 가 오류를 낸다
      expect(response.status).toBe(404);
      expect(response.body).toEqual({ detail: '게시판을 찾을 수 없습니다.' });
    },
  );
});

describe('글 고치기', () => {
  /** 글을 고친다. */
  async function edit(userId: string, id: string, body: object) {
    return request(app.getHttpServer())
      .patch(`${API}/posts/${id}`)
      .set(await as(userId))
      .send(body);
  }

  it('글쓴이가 보낸 칸만 고치고, 고친 글을 돌려준다', async () => {
    const id = await writtenId(WRITER);

    const response = await edit(WRITER, id, { title: '고친 제목' });

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({
      id,
      board: 'free',
      title: '고친 제목',
      content: '본문입니다.',
    });
    expect((await read(id)).body.title).toBe('고친 제목');
  });

  it('고치면 고친 시각이 바뀌고, 쓴 시각은 그대로다', async () => {
    const id = await writtenId(WRITER);
    const before = (await read(id)).body as Record<string, string>;

    const response = await edit(WRITER, id, { content: '고친 본문' });

    expect(response.body.created_at).toBe(before.created_at);
    expect(Date.parse(response.body.updated_at)).toBeGreaterThan(
      Date.parse(before.updated_at),
    );
  });

  it('남의 글은 고치지 못한다', async () => {
    const id = await writtenId(WRITER);

    const response = await edit(STRANGER, id, { title: '남이 고친 제목' });

    expect(response.status).toBe(403);
    expect(response.body).toEqual({ detail: '자신의 글만 고칠 수 있습니다.' });
    expect((await read(id)).body.title).toBe('첫 글');
  });

  it('운영자도 남의 글은 고치지 못한다', async () => {
    await makeOperator(app, OPERATOR);
    const id = await writtenId(WRITER);

    const response = await edit(OPERATOR, id, { title: '운영자가 고친 제목' });

    expect(response.status).toBe(403);
  });

  it('로그인하지 않으면 401 이다', async () => {
    const id = await writtenId(WRITER);

    const response = await request(app.getHttpServer())
      .patch(`${API}/posts/${id}`)
      .send({ title: '고친 제목' });

    expect(response.status).toBe(401);
  });

  it('없는 글이면 404 다', async () => {
    const response = await edit(WRITER, '999', { title: '고친 제목' });

    expect(response.status).toBe(404);
  });

  it('고칠 칸을 하나도 보내지 않으면 400 이다', async () => {
    const id = await writtenId(WRITER);

    const response = await edit(WRITER, id, {});

    expect(response.status).toBe(400);
    expect(response.body).toEqual({ detail: '고칠 내용을 적어야 합니다.' });
  });

  it('입력이 틀리면 400 이고 고치지 않는다', async () => {
    const id = await writtenId(WRITER);

    const response = await edit(WRITER, id, { title: '   ' });

    expect(response.status).toBe(400);
    expect((await read(id)).body.title).toBe('첫 글');
  });

  it('게시판은 옮길 수 없다', async () => {
    const id = await writtenId(WRITER);

    const response = await edit(WRITER, id, { board: 'notice' });

    expect(response.status).toBe(400);
    expect(response.body.errors).toHaveProperty('board');
  });
});

describe('글 지우기', () => {
  /** 글을 지운다. */
  async function remove(userId: string, id: string) {
    return request(app.getHttpServer())
      .delete(`${API}/posts/${id}`)
      .set(await as(userId));
  }

  it('글쓴이가 지우면 204 이고, 그 뒤로는 없는 글이다', async () => {
    const id = await writtenId(WRITER);

    const response = await remove(WRITER, id);

    expect(response.status).toBe(204);
    expect(response.text).toBe('');
    expect((await read(id)).status).toBe(404);
  });

  it('지운 글은 목록에도 전체 개수에도 들지 않는다', async () => {
    const kept = await writtenId(WRITER, 'free', '남는 글');
    const removed = await writtenId(WRITER, 'free', '지울 글');

    await remove(WRITER, removed);
    const response = await list();

    expect(response.body.total).toBe(1);
    expect(response.body.items).toHaveLength(1);
    expect(response.body.items[0].id).toBe(kept);
  });

  it('행은 남기고 지운 시각을 적는다', async () => {
    const id = await writtenId(WRITER);

    await remove(WRITER, id);
    const row = await readPostRow(app, id);

    expect(row).toMatchObject({ id, title: '첫 글' });
    expect(row?.deleted_at).toBeInstanceOf(Date);
  });

  it('남의 글은 지우지 못한다', async () => {
    const id = await writtenId(WRITER);

    const response = await remove(STRANGER, id);

    expect(response.status).toBe(403);
    expect(response.body).toEqual({ detail: '자신의 글만 지울 수 있습니다.' });
    expect((await read(id)).status).toBe(200);
  });

  it('운영자는 남의 글도 지운다', async () => {
    await makeOperator(app, OPERATOR);
    const id = await writtenId(WRITER);

    const response = await remove(OPERATOR, id);

    expect(response.status).toBe(204);
    expect((await read(id)).status).toBe(404);
  });

  it('로그인하지 않으면 401 이다', async () => {
    const id = await writtenId(WRITER);

    const response = await request(app.getHttpServer()).delete(
      `${API}/posts/${id}`,
    );

    expect(response.status).toBe(401);
    expect((await read(id)).status).toBe(200);
  });

  it('없는 글이면 404 다', async () => {
    const response = await remove(WRITER, '999');

    expect(response.status).toBe(404);
  });

  it('이미 지운 글을 다시 지우면 404 다', async () => {
    const id = await writtenId(WRITER);
    await remove(WRITER, id);

    const response = await remove(WRITER, id);

    expect(response.status).toBe(404);
  });

  it('지운 글은 고칠 수 없다', async () => {
    const id = await writtenId(WRITER);
    await remove(WRITER, id);

    const response = await request(app.getHttpServer())
      .patch(`${API}/posts/${id}`)
      .set(await as(WRITER))
      .send({ title: '되살린 제목' });

    expect(response.status).toBe(404);
  });
});
