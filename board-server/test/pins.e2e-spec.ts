// board-server/test/pins.e2e-spec.ts

/**
 * 글 고정의 API 를 앱을 통째로 만들어 불러 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 *
 * 시간이 흘러 고정이 끝나는 것은 기다리지 않는다. 끝나는 시각을 DB 에서 지난 시각으로 바꿔 놓고 본다(test/data.ts).
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import {
  DEFAULT_PIN_DAYS,
  MAX_PIN_DAYS,
  MAX_PINS_PER_BOARD,
} from '../src/posts/pins.policy.js';
import { createTestApp, useKeys } from './app.js';
import { clearData, expirePin, makeOperator, readPostRow } from './data.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;
const DAY = 24 * 60 * 60 * 1000;

/** 테스트에 나오는 사람들. 인증 서버의 public_id 다 */
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const OPERATOR = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';

/** 글의 응답에서 테스트가 읽는 칸. */
interface Pinnable {
  id: string;
  pinned: boolean;
  pinned_until: string | null;
  comment_count: number;
  updated_at: string;
}

/** 글 목록의 응답에서 테스트가 읽는 칸. */
interface Listing {
  pinned: Pinnable[];
  items: Pinnable[];
  total: number;
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
async function writtenId(board = 'free', userId = WRITER): Promise<string> {
  const response = await request(app.getHttpServer())
    .post(`${API}/boards/${board}/posts`)
    .set(await as(userId))
    .send({ title: '글', content: '본문입니다.' });
  expect(response.status).toBe(201);
  return (response.body as Pinnable).id;
}

/** 글을 고정한다. body 를 주지 않으면 본문 없이 부른다. */
async function pin(userId: string, id: string, body?: object) {
  const call = request(app.getHttpServer())
    .put(`${API}/posts/${id}/pin`)
    .set(await as(userId));
  return body === undefined ? call : call.send(body);
}

/** 운영자로 글을 고정한다. 준비 단계에서 쓴다. */
async function pinned(id: string, body?: object): Promise<void> {
  expect((await pin(OPERATOR, id, body)).status).toBe(204);
}

/** 글의 고정을 푼다. */
async function unpin(userId: string, id: string) {
  return request(app.getHttpServer())
    .delete(`${API}/posts/${id}/pin`)
    .set(await as(userId));
}

/** 글 하나를 읽는다. */
async function read(id: string): Promise<Pinnable> {
  const response = await request(app.getHttpServer()).get(`${API}/posts/${id}`);
  expect(response.status).toBe(200);
  return response.body as Pinnable;
}

/** 글 목록을 읽는다. */
async function list(board = 'free', query = ''): Promise<Listing> {
  const response = await request(app.getHttpServer()).get(
    `${API}/boards/${board}/posts${query}`,
  );
  expect(response.status).toBe(200);
  return response.body as Listing;
}

/** 글 번호들만 뽑는다. */
function ids(posts: Pinnable[]): string[] {
  return posts.map((post) => post.id);
}

describe('글 고정하기', () => {
  it('운영자가 고정하면 204 이고 돌려주는 내용이 없다', async () => {
    const id = await writtenId();

    const response = await pin(OPERATOR, id);

    expect(response.status).toBe(204);
    expect(response.text).toBe('');
    expect((await read(id)).pinned).toBe(true);
  });

  it('며칠 동안인지 적지 않으면 정해 둔 기간만큼 고정한다', async () => {
    const id = await writtenId();
    const before = Date.now();

    await pinned(id);

    const until = Date.parse((await read(id)).pinned_until ?? '');
    expect(until).toBeGreaterThanOrEqual(before + DEFAULT_PIN_DAYS * DAY);
    expect(until).toBeLessThanOrEqual(Date.now() + DEFAULT_PIN_DAYS * DAY);
  });

  it('적은 날수만큼 고정한다', async () => {
    const id = await writtenId();
    const before = Date.now();

    await pinned(id, { days: 30 });

    const until = Date.parse((await read(id)).pinned_until ?? '');
    expect(until).toBeGreaterThanOrEqual(before + 30 * DAY);
    expect(until).toBeLessThanOrEqual(Date.now() + 30 * DAY);
  });

  it.each([0, -1, 1.5, MAX_PIN_DAYS + 1, '7', null])(
    'days 가 틀리면(%j) 400 이고 고정하지 않는다',
    async (days) => {
      const id = await writtenId();

      const response = await pin(OPERATOR, id, { days });

      expect(response.status).toBe(400);
      expect(response.body.errors).toHaveProperty('days');
      expect((await read(id)).pinned).toBe(false);
    },
  );

  it('모르는 칸을 보내면 400 이다', async () => {
    const id = await writtenId();

    const response = await pin(OPERATOR, id, { until: '2099-01-01' });

    expect(response.status).toBe(400);
    expect((await read(id)).pinned).toBe(false);
  });

  it('가장 긴 기간까지 받는다', async () => {
    const id = await writtenId();

    expect((await pin(OPERATOR, id, { days: MAX_PIN_DAYS })).status).toBe(204);
  });

  it('운영자가 아니면 403 이다. 글쓴이도 제 글을 고정하지 못한다', async () => {
    const id = await writtenId('free', WRITER);

    const response = await pin(WRITER, id);

    expect(response.status).toBe(403);
    expect(response.body).toEqual({
      detail: '운영자만 글을 고정할 수 있습니다.',
    });
    expect((await read(id)).pinned).toBe(false);
  });

  it('로그인하지 않으면 401 이다', async () => {
    const id = await writtenId();

    const response = await request(app.getHttpServer()).put(
      `${API}/posts/${id}/pin`,
    );

    expect(response.status).toBe(401);
    expect((await read(id)).pinned).toBe(false);
  });

  it('없는 글이면 404 다. 운영자가 아니어도 404 가 먼저다', async () => {
    expect((await pin(OPERATOR, '999')).status).toBe(404);
    expect((await pin(WRITER, '999')).status).toBe(404);
    expect((await pin(OPERATOR, 'abc')).status).toBe(404);
  });

  it('지운 글은 고정할 수 없다', async () => {
    const id = await writtenId();
    await request(app.getHttpServer())
      .delete(`${API}/posts/${id}`)
      .set(await as(WRITER));

    expect((await pin(OPERATOR, id)).status).toBe(404);
  });

  it('이미 고정한 글을 다시 고정하면 기간을 새로 잡는다', async () => {
    const id = await writtenId();
    await pinned(id, { days: 1 });
    const first = Date.parse((await read(id)).pinned_until ?? '');

    await pinned(id, { days: 10 });

    const second = Date.parse((await read(id)).pinned_until ?? '');
    expect(second - first).toBeGreaterThanOrEqual(9 * DAY);
  });

  it('고정해도 글을 고친 시각은 그대로다', async () => {
    const id = await writtenId();
    const before = (await read(id)).updated_at;

    await pinned(id);
    await unpin(OPERATOR, id);

    // 고정은 글을 고치는 것이 아니다. "수정됨" 표시가 붙으면 안 된다
    expect((await read(id)).updated_at).toBe(before);
  });

  it('어느 게시판의 글이든 고정한다', async () => {
    const notice = await writtenId('notice', OPERATOR);
    const free = await writtenId('free', WRITER);

    await pinned(notice);
    await pinned(free);

    expect(ids((await list('notice')).pinned)).toEqual([notice]);
    expect(ids((await list('free')).pinned)).toEqual([free]);
  });
});

describe('고정할 수 있는 글의 수', () => {
  /** 글을 n 개 써서 모두 고정한다. */
  async function pinMany(n: number, board = 'free'): Promise<string[]> {
    const written: string[] = [];
    for (let i = 0; i < n; i += 1) {
      const id = await writtenId(board);
      await pinned(id);
      written.push(id);
    }
    return written;
  }

  it('한 게시판에 정해 둔 수를 넘기면 409 다', async () => {
    await pinMany(MAX_PINS_PER_BOARD);
    const extra = await writtenId();

    const response = await pin(OPERATOR, extra);

    expect(response.status).toBe(409);
    expect(response.body).toEqual({
      detail: '이 게시판에는 글을 더 고정할 수 없습니다.',
    });
    expect((await read(extra)).pinned).toBe(false);
  });

  it('다 찼어도 이미 고정한 글은 다시 고정할 수 있다', async () => {
    const [first] = await pinMany(MAX_PINS_PER_BOARD);

    expect((await pin(OPERATOR, first, { days: 30 })).status).toBe(204);
  });

  it('하나를 풀면 자리가 난다', async () => {
    const [first] = await pinMany(MAX_PINS_PER_BOARD);
    const extra = await writtenId();

    await unpin(OPERATOR, first);

    expect((await pin(OPERATOR, extra)).status).toBe(204);
  });

  it('고정이 끝난 글은 자리를 차지하지 않는다', async () => {
    const [first] = await pinMany(MAX_PINS_PER_BOARD);
    const extra = await writtenId();

    await expirePin(app, first);

    expect((await pin(OPERATOR, extra)).status).toBe(204);
  });

  it('지운 글은 자리를 차지하지 않는다', async () => {
    const [first] = await pinMany(MAX_PINS_PER_BOARD);
    const extra = await writtenId();

    await request(app.getHttpServer())
      .delete(`${API}/posts/${first}`)
      .set(await as(OPERATOR));

    expect((await pin(OPERATOR, extra)).status).toBe(204);
  });

  it('게시판마다 따로 센다', async () => {
    await pinMany(MAX_PINS_PER_BOARD, 'free');
    const elsewhere = await writtenId('scenario');

    expect((await pin(OPERATOR, elsewhere)).status).toBe(204);
  });
});

describe('고정 풀기', () => {
  it('운영자가 풀면 204 이고 고정하지 않은 글이 된다', async () => {
    const id = await writtenId();
    await pinned(id);

    const response = await unpin(OPERATOR, id);

    expect(response.status).toBe(204);
    expect(await read(id)).toMatchObject({ pinned: false, pinned_until: null });
    expect(await readPostRow(app, id)).toMatchObject({
      pinned_at: null,
      pinned_until: null,
    });
  });

  it('고정하지 않은 글을 풀어도 오류가 아니다', async () => {
    const id = await writtenId();

    expect((await unpin(OPERATOR, id)).status).toBe(204);
    expect((await unpin(OPERATOR, id)).status).toBe(204);
  });

  it('운영자가 아니면 403 이고 고정은 그대로다', async () => {
    const id = await writtenId();
    await pinned(id);

    const response = await unpin(WRITER, id);

    expect(response.status).toBe(403);
    expect((await read(id)).pinned).toBe(true);
  });

  it('로그인하지 않으면 401 이다', async () => {
    const id = await writtenId();

    const response = await request(app.getHttpServer()).delete(
      `${API}/posts/${id}/pin`,
    );

    expect(response.status).toBe(401);
  });

  it('없는 글이면 404 다', async () => {
    expect((await unpin(OPERATOR, '999')).status).toBe(404);
  });
});

describe('글 목록의 고정한 글', () => {
  it('고정한 글은 pinned 에 따로 실리고 items 와 total 에는 들지 않는다', async () => {
    const first = await writtenId();
    const notice = await writtenId();
    const last = await writtenId();
    await pinned(notice);

    const listing = await list();

    expect(ids(listing.pinned)).toEqual([notice]);
    expect(ids(listing.items)).toEqual([last, first]);
    expect(listing.total).toBe(2);
    expect(listing.pinned[0]).toMatchObject({ pinned: true });
    expect(listing.items.every((post) => !post.pinned)).toBe(true);
  });

  it('고정한 글이 없으면 pinned 는 빈 목록이다', async () => {
    await writtenId();

    expect((await list()).pinned).toEqual([]);
  });

  it('나중에 고정한 글이 위에 온다', async () => {
    const older = await writtenId();
    const newer = await writtenId();
    await pinned(newer);
    await pinned(older);

    // 글을 쓴 차례가 아니라 고정한 차례다
    expect(ids((await list()).pinned)).toEqual([older, newer]);
  });

  it('다시 고정한 글은 맨 위로 올라온다', async () => {
    const first = await writtenId();
    const second = await writtenId();
    await pinned(first);
    await pinned(second);

    await pinned(first);

    expect(ids((await list()).pinned)).toEqual([first, second]);
  });

  it('고정한 글은 첫 쪽에만 싣는다', async () => {
    const notice = await writtenId();
    await writtenId();
    await writtenId();
    await writtenId();
    await pinned(notice);

    const firstPage = await list('free', '?size=2&page=1');
    const secondPage = await list('free', '?size=2&page=2');

    expect(ids(firstPage.pinned)).toEqual([notice]);
    expect(secondPage.pinned).toEqual([]);
  });

  it('고정한 글은 쪽의 크기에 세지 않는다', async () => {
    const notice = await writtenId();
    const a = await writtenId();
    const b = await writtenId();
    const c = await writtenId();
    await pinned(notice);

    const firstPage = await list('free', '?size=2&page=1');
    const secondPage = await list('free', '?size=2&page=2');

    // 고정한 글 하나에 더해 글 둘이 온다. 고정했다고 다른 글이 다음 쪽으로 밀리지 않는다
    expect(ids(firstPage.items)).toEqual([c, b]);
    expect(ids(secondPage.items)).toEqual([a]);
    expect(firstPage.total).toBe(3);
  });

  it('고정을 풀면 제 번호의 자리로 돌아온다', async () => {
    const first = await writtenId();
    const notice = await writtenId();
    const last = await writtenId();
    await pinned(notice);

    await unpin(OPERATOR, notice);

    const listing = await list();
    expect(listing.pinned).toEqual([]);
    expect(ids(listing.items)).toEqual([last, notice, first]);
    expect(listing.total).toBe(3);
  });

  it('다른 게시판의 고정한 글은 섞이지 않는다', async () => {
    const elsewhere = await writtenId('scenario');
    await writtenId('free');
    await pinned(elsewhere);

    expect((await list('free')).pinned).toEqual([]);
    expect(ids((await list('scenario')).pinned)).toEqual([elsewhere]);
  });

  it('고정한 글을 지우면 목록에서 빠진다', async () => {
    const notice = await writtenId();
    await pinned(notice);

    await request(app.getHttpServer())
      .delete(`${API}/posts/${notice}`)
      .set(await as(WRITER));

    const listing = await list();
    expect(listing.pinned).toEqual([]);
    expect(listing.items).toEqual([]);
  });

  it('고정한 글에도 댓글 수가 실린다', async () => {
    const notice = await writtenId();
    await pinned(notice);
    await request(app.getHttpServer())
      .post(`${API}/posts/${notice}/comments`)
      .set(await as(WRITER))
      .send({ content: '댓글입니다.' });

    expect((await list()).pinned[0].comment_count).toBe(1);
  });
});

describe('고정이 끝난 글', () => {
  it('끝나는 시각이 지나면 저절로 내려간다', async () => {
    const first = await writtenId();
    const notice = await writtenId();
    const last = await writtenId();
    await pinned(notice);

    await expirePin(app, notice);

    // 아무도 풀지 않았다. 읽을 때 고정하지 않은 글로 읽는다
    const listing = await list();
    expect(listing.pinned).toEqual([]);
    expect(ids(listing.items)).toEqual([last, notice, first]);
    expect(listing.total).toBe(3);
  });

  it('글 하나를 읽어도 고정하지 않은 글이다. 지난 시각은 내보내지 않는다', async () => {
    const notice = await writtenId();
    await pinned(notice);

    await expirePin(app, notice);

    expect(await read(notice)).toMatchObject({
      pinned: false,
      pinned_until: null,
    });
  });

  it('끝난 글을 다시 고정할 수 있다', async () => {
    const notice = await writtenId();
    await pinned(notice);
    await expirePin(app, notice);

    await pinned(notice);

    expect(ids((await list()).pinned)).toEqual([notice]);
  });
});
