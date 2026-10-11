// board-server/test/comment-counts.e2e-spec.ts

/**
 * 글에 실리는 댓글 수(comment_count)를 앱을 통째로 만들어 불러 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 *
 * 세는 것은 살아 있는 댓글과 답글이다. 지운 것은 세지 않는다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { DataSource } from 'typeorm';
import { API_PREFIX } from '../src/app.setup.js';
import { createTestApp, useKeys } from './app.js';
import { clearData } from './data.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;

/** 테스트에 나오는 사람들. 인증 서버의 public_id 다 */
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const STRANGER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';

/** 글의 응답에서 테스트가 읽는 칸. */
interface Counted {
  id: string;
  comment_count: number;
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

/** 이 사람의 토큰을 붙인 머리말. */
async function as(userId: string): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId })}`,
  };
}

/** 글을 쓴다. */
async function write(board = 'free', title = '글'): Promise<request.Response> {
  return request(app.getHttpServer())
    .post(`${API}/boards/${board}/posts`)
    .set(await as(WRITER))
    .send({ title, content: '본문입니다.' });
}

/** 글을 써서 그 번호를 돌려준다. */
async function writtenPostId(board = 'free', title = '글'): Promise<string> {
  const response = await write(board, title);
  expect(response.status).toBe(201);
  return (response.body as Counted).id;
}

/** 댓글을 달아 그 번호를 돌려준다. parentId 를 주면 답글이다. */
async function commentId(postId: string, parentId?: string): Promise<string> {
  const response = await request(app.getHttpServer())
    .post(`${API}/posts/${postId}/comments`)
    .set(await as(STRANGER))
    .send({ content: '댓글입니다.', parent_id: parentId });
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 댓글을 지운다. */
async function removeComment(id: string): Promise<void> {
  const response = await request(app.getHttpServer())
    .delete(`${API}/comments/${id}`)
    .set(await as(STRANGER));
  expect(response.status).toBe(204);
}

/** 글 하나를 읽어 그 댓글 수를 돌려준다. */
async function countOnPost(postId: string): Promise<number> {
  const response = await request(app.getHttpServer()).get(
    `${API}/posts/${postId}`,
  );
  expect(response.status).toBe(200);
  return (response.body as Counted).comment_count;
}

/** 글 목록을 읽어 글 번호마다의 댓글 수를 돌려준다. */
async function countsOnList(
  board = 'free',
  query = '',
): Promise<Record<string, number>> {
  const response = await request(app.getHttpServer()).get(
    `${API}/boards/${board}/posts${query}`,
  );
  expect(response.status).toBe(200);
  const items = (response.body as { items: Counted[] }).items;
  return Object.fromEntries(items.map((item) => [item.id, item.comment_count]));
}

describe('글 하나의 댓글 수', () => {
  it('방금 쓴 글은 0 이다', async () => {
    const response = await write();

    expect((response.body as Counted).comment_count).toBe(0);
  });

  it('댓글이 없는 글은 0 이다', async () => {
    const postId = await writtenPostId();

    expect(await countOnPost(postId)).toBe(0);
  });

  it('댓글과 답글을 함께 센다', async () => {
    const postId = await writtenPostId();
    const first = await commentId(postId);
    await commentId(postId);
    await commentId(postId, first);

    expect(await countOnPost(postId)).toBe(3);
  });

  it('지운 댓글은 세지 않는다', async () => {
    const postId = await writtenPostId();
    await commentId(postId);
    const removed = await commentId(postId);
    await removeComment(removed);

    expect(await countOnPost(postId)).toBe(1);
  });

  it('지운 답글은 세지 않는다', async () => {
    const postId = await writtenPostId();
    const parent = await commentId(postId);
    const reply = await commentId(postId, parent);
    await removeComment(reply);

    expect(await countOnPost(postId)).toBe(1);
  });

  it('답글이 남아 자리만 보이는 지운 댓글은 세지 않고, 그 답글은 센다', async () => {
    const postId = await writtenPostId();
    const parent = await commentId(postId);
    await commentId(postId, parent);
    await commentId(postId, parent);
    await removeComment(parent);

    // 화면에는 "삭제된 댓글입니다" 아래에 답글 둘이 보인다. 읽을 수 있는 글은 둘이다
    expect(await countOnPost(postId)).toBe(2);
  });

  it('다른 글의 댓글은 세지 않는다', async () => {
    const postId = await writtenPostId();
    const other = await writtenPostId();
    await commentId(other);
    await commentId(other);

    expect(await countOnPost(postId)).toBe(0);
  });

  it('글을 고친 응답에도 실린다', async () => {
    const postId = await writtenPostId();
    await commentId(postId);

    const response = await request(app.getHttpServer())
      .patch(`${API}/posts/${postId}`)
      .set(await as(WRITER))
      .send({ title: '고친 제목' });

    expect(response.status).toBe(200);
    expect((response.body as Counted).comment_count).toBe(1);
  });
});

describe('글 목록의 댓글 수', () => {
  it('글마다 제 댓글 수가 실린다', async () => {
    const quiet = await writtenPostId();
    const busy = await writtenPostId();
    const removedOnly = await writtenPostId();
    const parent = await commentId(busy);
    await commentId(busy, parent);
    await commentId(busy);
    await removeComment(await commentId(removedOnly));

    expect(await countsOnList()).toEqual({
      [quiet]: 0,
      [busy]: 3,
      // 달렸다가 지워진 댓글뿐인 글도 0 이다
      [removedOnly]: 0,
    });
  });

  it('다른 게시판의 글과 섞이지 않는다', async () => {
    const free = await writtenPostId('free');
    const scenario = await writtenPostId('scenario');
    await commentId(scenario);

    expect(await countsOnList('free')).toEqual({ [free]: 0 });
    expect(await countsOnList('scenario')).toEqual({ [scenario]: 1 });
  });

  it('글이 없는 게시판은 빈 목록이다', async () => {
    expect(await countsOnList()).toEqual({});
  });

  it('쪽을 넘겨도 그 쪽의 글에 맞는 수가 실린다', async () => {
    const first = await writtenPostId();
    const second = await writtenPostId();
    const third = await writtenPostId();
    await commentId(first);
    await commentId(third);
    await commentId(third);

    // 새 글부터다. 1쪽에 third 와 second, 2쪽에 first 가 온다
    expect(await countsOnList('free', '?size=2&page=1')).toEqual({
      [third]: 2,
      [second]: 0,
    });
    expect(await countsOnList('free', '?size=2&page=2')).toEqual({
      [first]: 1,
    });
  });

  it('한 쪽의 글이 많아도 쿼리 하나로 센다', async () => {
    for (let i = 0; i < 5; i += 1) {
      await commentId(await writtenPostId());
    }
    const queries: string[] = [];
    const dataSource = app.get(DataSource);
    const original = dataSource.driver.createQueryRunner.bind(
      dataSource.driver,
    );
    const spy = vi
      .spyOn(dataSource.driver, 'createQueryRunner')
      .mockImplementation((mode) => {
        const runner = original(mode);
        const run = runner.query.bind(runner);
        runner.query = ((query: string, ...rest: unknown[]) => {
          queries.push(query);
          return (run as (...args: unknown[]) => Promise<unknown>)(
            query,
            ...rest,
          );
        }) as typeof runner.query;
        return runner;
      });

    await countsOnList();
    spy.mockRestore();

    // 글마다 한 번씩 세면 글의 수만큼 쿼리가 는다
    const counting = queries.filter(
      (query) => query.includes('"comments"') && query.includes('COUNT'),
    );
    expect(counting).toHaveLength(1);
  });
});
