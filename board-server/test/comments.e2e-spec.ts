// board-server/test/comments.e2e-spec.ts

/**
 * 댓글과 답글의 API 를 앱을 통째로 만들어 불러 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 * 인증 서버는 띄우지 않는다. 테스트가 만든 키로 사용자마다 토큰을 서명한다.
 *
 * 테스트마다 글, 댓글, 운영자를 비우고 시작한다. 글은 테스트가 자유 게시판(free)에 써 둔다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { MAX_REPLIES_PER_COMMENT } from '../src/comments/comments.policy.js';
import { createTestApp, useKeys } from './app.js';
import { clearData, makeOperator, readCommentRow } from './data.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;

/** 테스트에 나오는 사람들. 인증 서버의 public_id 다 */
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const STRANGER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const OPERATOR = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';

/** 목록의 한 줄. 테스트가 읽는 칸만 적는다. */
interface Thread {
  id: string;
  content: string | null;
  author_id: string | null;
  deleted: boolean;
  replies: { id: string; content: string | null }[];
}

let app: NestExpressApplication;
let key: SigningKey;
/** 테스트마다 새로 써 두는 글의 번호 */
let postId: string;

beforeAll(async () => {
  key = await makeSigningKey('key-1');
  app = await createTestApp(useKeys(() => publicKeys(key)));
});

afterAll(async () => {
  await app.close();
});

beforeEach(async () => {
  await clearData(app);
  postId = await writtenPostId();
});

/** 이 사람의 토큰을 붙인 머리말. */
async function as(userId: string): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId })}`,
  };
}

/** 글을 써서 그 번호를 돌려준다. */
async function writtenPostId(board = 'free', userId = WRITER): Promise<string> {
  const response = await request(app.getHttpServer())
    .post(`${API}/boards/${board}/posts`)
    .set(await as(userId))
    .send({ title: '글', content: '본문입니다.' });
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 글에 댓글을 단다. parentId 를 주면 답글이다. */
async function comment(
  userId: string,
  body: object = { content: '댓글입니다.' },
  post = postId,
): Promise<request.Response> {
  return request(app.getHttpServer())
    .post(`${API}/posts/${post}/comments`)
    .set(await as(userId))
    .send(body);
}

/** 댓글을 달아 그 번호를 돌려준다. 준비 단계에서 쓴다. */
async function commentId(
  userId: string,
  content = '댓글입니다.',
  parentId?: string,
): Promise<string> {
  const response = await comment(userId, { content, parent_id: parentId });
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 댓글 목록을 읽는다. 로그인하지 않는다. */
function list(query = '', post = postId): request.Test {
  return request(app.getHttpServer()).get(
    `${API}/posts/${post}/comments${query}`,
  );
}

/** 댓글 목록의 줄들을 읽는다. */
async function threads(query = ''): Promise<Thread[]> {
  const response = await list(query);
  expect(response.status).toBe(200);
  return (response.body as { items: Thread[] }).items;
}

/** 댓글을 고친다. */
async function edit(userId: string, id: string, body: object) {
  return request(app.getHttpServer())
    .patch(`${API}/comments/${id}`)
    .set(await as(userId))
    .send(body);
}

/** 댓글을 지운다. */
async function remove(userId: string, id: string) {
  return request(app.getHttpServer())
    .delete(`${API}/comments/${id}`)
    .set(await as(userId));
}

describe('댓글 쓰기', () => {
  it('로그인한 사람이 달면 201 과 쓴 댓글을 돌려준다', async () => {
    const response = await comment(STRANGER);

    expect(response.status).toBe(201);
    expect(response.body).toEqual({
      id: '1',
      post_id: postId,
      parent_id: null,
      author_id: STRANGER,
      content: '댓글입니다.',
      deleted: false,
      created_at: expect.any(String),
      updated_at: expect.any(String),
    });
  });

  it('parent_id 가 null 이면 글에 다는 댓글이다', async () => {
    const response = await comment(WRITER, {
      content: '댓글',
      parent_id: null,
    });

    expect(response.status).toBe(201);
    expect(response.body.parent_id).toBeNull();
  });

  it('로그인하지 않으면 401 이다', async () => {
    const response = await request(app.getHttpServer())
      .post(`${API}/posts/${postId}/comments`)
      .send({ content: '댓글입니다.' });

    expect(response.status).toBe(401);
  });

  it('없는 글이면 404 다', async () => {
    const response = await comment(WRITER, { content: '댓글' }, '999');

    expect(response.status).toBe(404);
    expect(response.body).toEqual({ detail: '글을 찾을 수 없습니다.' });
  });

  it('지운 글에는 달지 못한다', async () => {
    await request(app.getHttpServer())
      .delete(`${API}/posts/${postId}`)
      .set(await as(WRITER));

    const response = await comment(STRANGER);

    expect(response.status).toBe(404);
  });

  it('입력이 틀리면 400 이고 저장하지 않는다', async () => {
    const response = await comment(WRITER, { content: '   ' });

    expect(response.status).toBe(400);
    expect(response.body.errors).toHaveProperty('content');
    expect(await threads()).toEqual([]);
  });

  it('글쓴이는 토큰의 주인이다. 본문으로 정할 수 없다', async () => {
    const response = await comment(WRITER, {
      content: '댓글',
      author_id: STRANGER,
    });

    expect(response.status).toBe(400);
  });

  it('운영자만 글을 쓰는 게시판의 글에도 댓글은 누구나 단다', async () => {
    await makeOperator(app, OPERATOR);
    const notice = await writtenPostId('notice', OPERATOR);

    const response = await comment(
      STRANGER,
      { content: '확인했습니다.' },
      notice,
    );

    expect(response.status).toBe(201);
  });
});

describe('답글 쓰기', () => {
  it('댓글에 답글을 단다', async () => {
    const parent = await commentId(WRITER);

    const response = await comment(STRANGER, {
      content: '답글입니다.',
      parent_id: parent,
    });

    expect(response.status).toBe(201);
    expect(response.body).toMatchObject({
      post_id: postId,
      parent_id: parent,
      author_id: STRANGER,
      content: '답글입니다.',
    });
  });

  it('답글에는 답글을 달지 못한다', async () => {
    const parent = await commentId(WRITER);
    const reply = await commentId(STRANGER, '답글', parent);

    const response = await comment(WRITER, {
      content: '답글의 답글',
      parent_id: reply,
    });

    expect(response.status).toBe(400);
    expect(response.body).toEqual({
      detail: '답글에는 답글을 달 수 없습니다.',
    });
  });

  it('없는 댓글에는 답글을 달지 못한다', async () => {
    const response = await comment(WRITER, {
      content: '답글',
      parent_id: '999',
    });

    expect(response.status).toBe(400);
    expect(response.body).toEqual({
      detail: '답글을 달 댓글을 찾을 수 없습니다.',
    });
  });

  it('지운 댓글에는 답글을 달지 못한다', async () => {
    const parent = await commentId(WRITER);
    await remove(WRITER, parent);

    const response = await comment(STRANGER, {
      content: '답글',
      parent_id: parent,
    });

    expect(response.status).toBe(400);
  });

  it('다른 글의 댓글에는 답글을 달지 못한다', async () => {
    const parent = await commentId(WRITER);
    const otherPost = await writtenPostId();

    const response = await comment(
      WRITER,
      { content: '답글', parent_id: parent },
      otherPost,
    );

    // 이 글의 주소로 다른 글의 댓글 아래에 답글을 끼워 넣을 수 없다
    expect(response.status).toBe(400);
    expect(response.body).toEqual({
      detail: '답글을 달 댓글을 찾을 수 없습니다.',
    });
  });

  it('parent_id 가 댓글 번호의 모양이 아니면 400 이다', async () => {
    const response = await comment(WRITER, {
      content: '답글',
      parent_id: 'abc',
    });

    expect(response.status).toBe(400);
    expect(response.body.errors).toHaveProperty('parent_id');
  });

  it('한 댓글에 달 수 있는 답글이 다 차면 409 다', async () => {
    const parent = await commentId(WRITER);
    for (let number = 1; number <= MAX_REPLIES_PER_COMMENT; number += 1) {
      await commentId(STRANGER, `답글 ${number}`, parent);
    }

    const response = await comment(STRANGER, {
      content: '하나 더',
      parent_id: parent,
    });

    expect(response.status).toBe(409);
    expect(response.body).toEqual({
      detail: '이 댓글에는 답글을 더 달 수 없습니다.',
    });
  });

  it('지운 답글은 답글의 수에 세지 않는다', async () => {
    const parent = await commentId(WRITER);
    const replies: string[] = [];
    for (let number = 1; number <= MAX_REPLIES_PER_COMMENT; number += 1) {
      replies.push(await commentId(STRANGER, `답글 ${number}`, parent));
    }
    await remove(STRANGER, replies[0]);

    const response = await comment(STRANGER, {
      content: '빈자리에 하나 더',
      parent_id: parent,
    });

    expect(response.status).toBe(201);
  });
});

describe('댓글 목록', () => {
  it('로그인 없이, 먼저 쓴 것부터, 답글을 붙여 돌려준다', async () => {
    const first = await commentId(WRITER, '첫 댓글');
    const second = await commentId(STRANGER, '둘째 댓글');
    const reply = await commentId(STRANGER, '첫 댓글의 답글', first);

    const response = await list();

    expect(response.status).toBe(200);
    expect(response.body).toEqual({
      items: [
        {
          id: first,
          post_id: postId,
          parent_id: null,
          author_id: WRITER,
          content: '첫 댓글',
          deleted: false,
          created_at: expect.any(String),
          updated_at: expect.any(String),
          replies: [
            {
              id: reply,
              post_id: postId,
              parent_id: first,
              author_id: STRANGER,
              content: '첫 댓글의 답글',
              deleted: false,
              created_at: expect.any(String),
              updated_at: expect.any(String),
            },
          ],
        },
        expect.objectContaining({
          id: second,
          content: '둘째 댓글',
          replies: [],
        }),
      ],
      next: null,
    });
  });

  it('댓글이 없으면 빈 목록이다', async () => {
    const response = await list();

    expect(response.body).toEqual({ items: [], next: null });
  });

  it('답글은 댓글별로, 먼저 쓴 것부터다', async () => {
    const first = await commentId(WRITER, '첫 댓글');
    const second = await commentId(WRITER, '둘째 댓글');
    await commentId(STRANGER, '둘째의 답글 1', second);
    await commentId(STRANGER, '첫째의 답글 1', first);
    await commentId(STRANGER, '둘째의 답글 2', second);

    const [one, two] = await threads();

    expect(one.replies.map((reply) => reply.content)).toEqual([
      '첫째의 답글 1',
    ]);
    expect(two.replies.map((reply) => reply.content)).toEqual([
      '둘째의 답글 1',
      '둘째의 답글 2',
    ]);
  });

  it('그 글의 댓글만 돌려준다', async () => {
    await commentId(WRITER, '이 글의 댓글');
    const otherPost = await writtenPostId();
    await comment(WRITER, { content: '다른 글의 댓글' }, otherPost);

    const items = await threads();

    expect(items.map((item) => item.content)).toEqual(['이 글의 댓글']);
  });

  it('"이것 다음 몇 개"로 이어 읽는다. 답글은 개수에 세지 않는다', async () => {
    const ids: string[] = [];
    for (let number = 1; number <= 5; number += 1) {
      ids.push(await commentId(WRITER, `댓글 ${number}`));
    }
    await commentId(STRANGER, '답글', ids[0]);

    const first = await list('?size=2');
    const second = await list(`?size=2&after=${first.body.next}`);
    const third = await list(`?size=2&after=${second.body.next}`);
    const contents = (response: request.Response): (string | null)[] =>
      (response.body.items as Thread[]).map((item) => item.content);

    expect(contents(first)).toEqual(['댓글 1', '댓글 2']);
    expect(first.body.items[0].replies).toHaveLength(1);
    expect(first.body.next).toBe(ids[1]);
    expect(contents(second)).toEqual(['댓글 3', '댓글 4']);
    expect(contents(third)).toEqual(['댓글 5']);
    // 뒤에 더 없으면 next 가 비어 있다
    expect(third.body.next).toBeNull();
  });

  it('딱 맞게 끝나면 next 가 비어 있다', async () => {
    await commentId(WRITER, '댓글 1');
    await commentId(WRITER, '댓글 2');

    const response = await list('?size=2');

    expect(response.body.items).toHaveLength(2);
    expect(response.body.next).toBeNull();
  });

  it('읽는 사이에 새 댓글이 달려도 겹치거나 빠지지 않는다', async () => {
    await commentId(WRITER, '댓글 1');
    await commentId(WRITER, '댓글 2');
    await commentId(WRITER, '댓글 3');
    const first = await list('?size=2');

    await commentId(STRANGER, '그사이에 달린 댓글');
    const second = await list(`?size=2&after=${first.body.next}`);

    expect((second.body.items as Thread[]).map((item) => item.content)).toEqual(
      ['댓글 3', '그사이에 달린 댓글'],
    );
  });

  it('번호가 열 자리를 넘어가도 작은 번호가 먼저다', async () => {
    // 글자로 줄 세우면 '10' 이 '9' 보다 앞에 온다. 숫자로 줄 세우는지 본다
    for (let number = 1; number <= 11; number += 1) {
      await commentId(WRITER, `댓글 ${number}`);
    }

    const response = await list('?size=3&after=8');

    expect((response.body.items as Thread[]).map((item) => item.id)).toEqual([
      '9',
      '10',
      '11',
    ]);
  });

  it.each(['?after=abc', '?after=0', '?size=0', '?size=51', '?page=2'])(
    '주소에 붙인 값이 틀리면(%s) 400 이다',
    async (query) => {
      const response = await list(query);

      expect(response.status).toBe(400);
    },
  );

  it('없는 글이면 404 다', async () => {
    const response = await list('', '999');

    expect(response.status).toBe(404);
    expect(response.body).toEqual({ detail: '글을 찾을 수 없습니다.' });
  });

  it('지운 글의 댓글은 읽을 수 없다', async () => {
    await commentId(STRANGER);
    await request(app.getHttpServer())
      .delete(`${API}/posts/${postId}`)
      .set(await as(WRITER));

    const response = await list();

    expect(response.status).toBe(404);
  });
});

describe('댓글 고치기', () => {
  it('글쓴이가 내용을 고치고, 고친 댓글을 돌려준다', async () => {
    const id = await commentId(WRITER);

    const response = await edit(WRITER, id, { content: '고친 댓글' });

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({ id, content: '고친 댓글' });
    expect((await threads())[0].content).toBe('고친 댓글');
  });

  it('고치면 고친 시각이 바뀌고, 쓴 시각은 그대로다', async () => {
    const created = await comment(WRITER);

    const response = await edit(WRITER, created.body.id, {
      content: '고친 댓글',
    });

    expect(response.body.created_at).toBe(created.body.created_at);
    expect(Date.parse(response.body.updated_at)).toBeGreaterThan(
      Date.parse(created.body.updated_at),
    );
  });

  it('답글도 고친다. 어느 댓글의 답글인지는 그대로다', async () => {
    const parent = await commentId(WRITER);
    const reply = await commentId(STRANGER, '답글', parent);

    const response = await edit(STRANGER, reply, { content: '고친 답글' });

    expect(response.body).toMatchObject({
      parent_id: parent,
      content: '고친 답글',
    });
  });

  it('남의 댓글은 고치지 못한다', async () => {
    const id = await commentId(WRITER);

    const response = await edit(STRANGER, id, { content: '남이 고친 댓글' });

    expect(response.status).toBe(403);
    expect(response.body).toEqual({
      detail: '자신의 댓글만 고칠 수 있습니다.',
    });
    expect((await threads())[0].content).toBe('댓글입니다.');
  });

  it('운영자도 남의 댓글은 고치지 못한다', async () => {
    await makeOperator(app, OPERATOR);
    const id = await commentId(WRITER);

    const response = await edit(OPERATOR, id, {
      content: '운영자가 고친 댓글',
    });

    expect(response.status).toBe(403);
  });

  it('로그인하지 않으면 401 이다', async () => {
    const id = await commentId(WRITER);

    const response = await request(app.getHttpServer())
      .patch(`${API}/comments/${id}`)
      .send({ content: '고친 댓글' });

    expect(response.status).toBe(401);
  });

  it.each(['999', 'abc', '0'])('없는 댓글(%s)이면 404 다', async (id) => {
    const response = await edit(WRITER, id, { content: '고친 댓글' });

    expect(response.status).toBe(404);
    expect(response.body).toEqual({ detail: '댓글을 찾을 수 없습니다.' });
  });

  it('내용을 보내지 않으면 400 이다', async () => {
    const id = await commentId(WRITER);

    const response = await edit(WRITER, id, {});

    expect(response.status).toBe(400);
    expect(response.body.errors).toHaveProperty('content');
  });
});

describe('댓글 지우기', () => {
  it('글쓴이가 지우면 204 이고 목록에서 빠진다', async () => {
    const kept = await commentId(WRITER, '남는 댓글');
    const removed = await commentId(WRITER, '지울 댓글');

    const response = await remove(WRITER, removed);

    expect(response.status).toBe(204);
    expect((await threads()).map((item) => item.id)).toEqual([kept]);
  });

  it('행은 남기고 지운 시각을 적는다', async () => {
    const id = await commentId(WRITER);

    await remove(WRITER, id);
    const row = await readCommentRow(app, id);

    expect(row).toMatchObject({ id, content: '댓글입니다.' });
    expect(row?.deleted_at).toBeInstanceOf(Date);
  });

  it('답글이 달린 댓글을 지우면 자리는 남고, 누가 무엇을 썼는지는 내보내지 않는다', async () => {
    const parent = await commentId(WRITER, '지울 댓글');
    const reply = await commentId(STRANGER, '남는 답글', parent);

    await remove(WRITER, parent);
    const items = await threads();

    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      id: parent,
      author_id: null,
      content: null,
      deleted: true,
    });
    expect(items[0].replies.map((item) => item.id)).toEqual([reply]);
  });

  it('지운 댓글의 답글까지 모두 지우면 자리도 사라진다', async () => {
    const parent = await commentId(WRITER, '지울 댓글');
    const reply = await commentId(STRANGER, '지울 답글', parent);
    await remove(WRITER, parent);

    await remove(STRANGER, reply);

    expect(await threads()).toEqual([]);
  });

  it('지운 답글은 목록에서 빠지고, 댓글은 그대로다', async () => {
    const parent = await commentId(WRITER, '댓글');
    const kept = await commentId(STRANGER, '남는 답글', parent);
    const removed = await commentId(STRANGER, '지울 답글', parent);

    await remove(STRANGER, removed);
    const [item] = await threads();

    expect(item).toMatchObject({ id: parent, deleted: false });
    expect(item.replies.map((reply) => reply.id)).toEqual([kept]);
  });

  it('자리만 남은 댓글도 이어 읽기의 차례에 든다', async () => {
    const first = await commentId(WRITER, '지울 댓글');
    await commentId(STRANGER, '답글', first);
    await commentId(WRITER, '둘째 댓글');
    await commentId(WRITER, '셋째 댓글');
    await remove(WRITER, first);

    const head = await list('?size=1');
    const rest = await list(`?size=5&after=${head.body.next}`);

    expect(head.body.items[0]).toMatchObject({ id: first, deleted: true });
    expect((rest.body.items as Thread[]).map((item) => item.content)).toEqual([
      '둘째 댓글',
      '셋째 댓글',
    ]);
  });

  it('남의 댓글은 지우지 못한다', async () => {
    const id = await commentId(WRITER);

    const response = await remove(STRANGER, id);

    expect(response.status).toBe(403);
    expect(response.body).toEqual({
      detail: '자신의 댓글만 지울 수 있습니다.',
    });
    expect(await threads()).toHaveLength(1);
  });

  it('글의 글쓴이라도 남의 댓글은 지우지 못한다', async () => {
    // 글은 WRITER 가 썼다. 댓글은 STRANGER 의 것이다
    const id = await commentId(STRANGER);

    const response = await remove(WRITER, id);

    expect(response.status).toBe(403);
  });

  it('운영자는 남의 댓글도 지운다', async () => {
    await makeOperator(app, OPERATOR);
    const id = await commentId(WRITER);

    const response = await remove(OPERATOR, id);

    expect(response.status).toBe(204);
    expect(await threads()).toEqual([]);
  });

  it('로그인하지 않으면 401 이다', async () => {
    const id = await commentId(WRITER);

    const response = await request(app.getHttpServer()).delete(
      `${API}/comments/${id}`,
    );

    expect(response.status).toBe(401);
    expect(await threads()).toHaveLength(1);
  });

  it('없는 댓글이면 404 다', async () => {
    const response = await remove(WRITER, '999');

    expect(response.status).toBe(404);
  });

  it('이미 지운 댓글은 다시 지우거나 고칠 수 없다', async () => {
    const id = await commentId(WRITER);
    await remove(WRITER, id);

    const again = await remove(WRITER, id);
    const edited = await edit(WRITER, id, { content: '되살린 댓글' });

    expect(again.status).toBe(404);
    expect(edited.status).toBe(404);
  });
});
