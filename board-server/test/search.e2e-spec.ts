// board-server/test/search.e2e-spec.ts

/**
 * 글 검색의 API 를 앱을 통째로 만들어 불러 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { createTestApp, useKeys } from './app.js';
import { clearData, makeOperator } from './data.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;

/** 테스트에 나오는 사람들. 인증 서버의 public_id 다 */
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const OPERATOR = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';

/** 검색 결과의 한 줄에서 테스트가 읽는 칸. */
interface Found {
  id: string;
  board: string;
  title: string;
  comment_count: number;
  pinned: boolean;
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
  await makeOperator(app, OPERATOR);
});

/** 이 사람의 토큰을 붙인 머리말. */
async function as(userId: string): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId })}`,
  };
}

/** 글을 써서 그 번호를 돌려준다. */
async function writtenId(
  title: string,
  content = '본문입니다.',
  board = 'free',
): Promise<string> {
  const response = await request(app.getHttpServer())
    .post(`${API}/boards/${board}/posts`)
    .set(await as(board === 'notice' ? OPERATOR : WRITER))
    .send({ title, content });
  expect(response.status).toBe(201);
  return (response.body as Found).id;
}

/** 글을 검색한다. 로그인하지 않는다. params 는 주소에 붙일 값이다. */
function search(params: Record<string, string | string[]>): request.Test {
  return request(app.getHttpServer()).get(`${API}/posts`).query(params);
}

/** 검색해서 찾은 글의 번호들을 돌려준다. */
async function foundIds(
  q: string,
  more: Record<string, string> = {},
): Promise<string[]> {
  const response = await search({ q, ...more });
  expect(response.status).toBe(200);
  return (response.body as { items: Found[] }).items.map((item) => item.id);
}

describe('글 검색', () => {
  it('로그인 없이 찾고, 글 목록과 같은 모양으로 돌려준다', async () => {
    const id = await writtenId('고정 버그를 찾았습니다', '본문에는 없는 말');

    const response = await search({ q: '버그' });

    expect(response.status).toBe(200);
    expect(response.body).toEqual({
      items: [
        {
          id,
          board: 'free',
          author_id: WRITER,
          author_nickname: null,
          title: '고정 버그를 찾았습니다',
          comment_count: 0,
          pinned: false,
          pinned_until: null,
          created_at: expect.any(String),
          updated_at: expect.any(String),
        },
      ],
      page: 1,
      size: 20,
      total: 1,
    });
  });

  it('제목에서도 본문에서도 찾는다', async () => {
    const inTitle = await writtenId('주사위 이야기', '본문입니다.');
    const inContent = await writtenId('제목', '어제 주사위를 굴렸다.');
    await writtenId('상관없는 글', '상관없는 본문');

    expect(await foundIds('주사위')).toEqual([inContent, inTitle]);
  });

  it('낱말의 어디에 있든 찾는다. 조사가 붙어도 찾는다', async () => {
    const id = await writtenId('공지사항을 읽어 주세요');

    expect(await foundIds('공지')).toEqual([id]);
    expect(await foundIds('지사')).toEqual([id]);
  });

  it('낱말이 모두 들어 있는 글만 찾는다', async () => {
    const both = await writtenId('고정 기능', '버그가 있습니다');
    await writtenId('고정 기능', '잘 됩니다');
    await writtenId('다른 글', '버그가 있습니다');

    // 한 낱말은 제목에, 다른 낱말은 본문에 있어도 된다
    expect(await foundIds('고정 버그')).toEqual([both]);
    expect(await foundIds('버그   고정')).toEqual([both]);
  });

  it('대소문자를 가리지 않는다', async () => {
    const id = await writtenId('NestJS 질문');

    expect(await foundIds('nestjs')).toEqual([id]);
    expect(await foundIds('NESTJS')).toEqual([id]);
  });

  it('새 글부터 돌려준다', async () => {
    const first = await writtenId('주사위 하나');
    const second = await writtenId('주사위 둘');
    const third = await writtenId('주사위 셋');

    expect(await foundIds('주사위')).toEqual([third, second, first]);
  });

  it('찾은 글이 없으면 빈 목록이다', async () => {
    await writtenId('주사위 이야기');

    const response = await search({ q: '없는낱말' });

    expect(response.status).toBe(200);
    expect(response.body).toEqual({ items: [], page: 1, size: 20, total: 0 });
  });

  it('본문은 싣지 않는다', async () => {
    await writtenId('주사위 이야기', '길고 긴 본문');

    const response = await search({ q: '주사위' });

    expect(response.body.items[0]).not.toHaveProperty('content');
  });
});

describe('검색어의 기호', () => {
  it('% 는 글자로 찾는다. "아무 글자나"가 아니다', async () => {
    const percent = await writtenId('확률은 50%입니다');
    await writtenId('확률은 500입니다');

    expect(await foundIds('50%')).toEqual([percent]);
  });

  it('_ 는 글자로 찾는다. "아무 한 글자"가 아니다', async () => {
    const underscore = await writtenId('snake_case 로 적는다');
    await writtenId('snakeXcase 로 적는다');

    expect(await foundIds('snake_case')).toEqual([underscore]);
  });

  it('역빗금도 글자로 찾는다', async () => {
    const backslash = await writtenId('경로는 C:\\temp 입니다');
    await writtenId('경로는 C:temp 입니다');

    expect(await foundIds('C:\\temp')).toEqual([backslash]);
  });

  it('SQL 로 읽힐 글자를 넣어도 글자로 찾는다', async () => {
    const quoted = await writtenId("제목에 '; DROP TABLE posts; -- 이 있다");
    await writtenId('평범한 글');

    expect(await foundIds("'; DROP TABLE posts; --")).toEqual([quoted]);
    // 글이 지워지지도 않았다
    expect(await foundIds('평범한')).toHaveLength(1);
  });
});

describe('검색의 범위', () => {
  it('게시판을 적지 않으면 모든 게시판에서 찾는다', async () => {
    const inFree = await writtenId('주사위 이야기', '본문', 'free');
    const inScenario = await writtenId('주사위 시나리오', '본문', 'scenario');
    const inNotice = await writtenId('주사위 공지', '본문', 'notice');

    const response = await search({ q: '주사위' });

    expect(response.body.total).toBe(3);
    // 글마다 어느 게시판의 글인지 실린다
    expect(
      (response.body.items as Found[]).map((item) => [item.id, item.board]),
    ).toEqual([
      [inNotice, 'notice'],
      [inScenario, 'scenario'],
      [inFree, 'free'],
    ]);
  });

  it('게시판을 적으면 그 게시판에서만 찾는다', async () => {
    const inFree = await writtenId('주사위 이야기', '본문', 'free');
    await writtenId('주사위 시나리오', '본문', 'scenario');

    expect(await foundIds('주사위', { board: 'free' })).toEqual([inFree]);
  });

  it('없는 게시판이면 404 다', async () => {
    const response = await search({ q: '주사위', board: 'no-such-board' });

    expect(response.status).toBe(404);
    expect(response.body).toEqual({ detail: '게시판을 찾을 수 없습니다.' });
  });

  it('지운 글은 나오지 않는다', async () => {
    const kept = await writtenId('주사위 하나');
    const removed = await writtenId('주사위 둘');
    await request(app.getHttpServer())
      .delete(`${API}/posts/${removed}`)
      .set(await as(WRITER));

    const response = await search({ q: '주사위' });

    expect(response.body.total).toBe(1);
    expect(response.body.items[0].id).toBe(kept);
  });

  it('고정한 글은 다른 글과 같이 제 번호의 자리에 나온다', async () => {
    const first = await writtenId('주사위 하나');
    const pinned = await writtenId('주사위 둘');
    const last = await writtenId('주사위 셋');
    await request(app.getHttpServer())
      .put(`${API}/posts/${pinned}/pin`)
      .set(await as(OPERATOR));

    const response = await search({ q: '주사위' });

    // 글 목록처럼 따로 싣지 않는다. 찾은 글을 새 글부터 보여 줄 뿐이다
    expect(response.body).not.toHaveProperty('pinned');
    expect(
      (response.body.items as Found[]).map((item) => [item.id, item.pinned]),
    ).toEqual([
      [last, false],
      [pinned, true],
      [first, false],
    ]);
  });

  it('찾은 글에 댓글 수가 실린다', async () => {
    const id = await writtenId('주사위 이야기');
    await request(app.getHttpServer())
      .post(`${API}/posts/${id}/comments`)
      .set(await as(WRITER))
      .send({ content: '댓글입니다.' });

    const response = await search({ q: '주사위' });

    expect(response.body.items[0].comment_count).toBe(1);
  });

  it('댓글에서는 찾지 않는다', async () => {
    const id = await writtenId('제목');
    await request(app.getHttpServer())
      .post(`${API}/posts/${id}/comments`)
      .set(await as(WRITER))
      .send({ content: '댓글에만 있는 낱말 주사위' });

    expect(await foundIds('주사위')).toEqual([]);
  });
});

describe('검색 결과의 쪽', () => {
  it('쪽으로 나누고 전체 개수를 함께 돌려준다', async () => {
    const ids: string[] = [];
    for (let i = 1; i <= 5; i += 1) {
      ids.push(await writtenId(`주사위 ${i}`));
    }
    await writtenId('상관없는 글');

    const first = await search({ q: '주사위', size: '2', page: '1' });
    const third = await search({ q: '주사위', size: '2', page: '3' });

    expect(first.body).toMatchObject({ page: 1, size: 2, total: 5 });
    expect((first.body.items as Found[]).map((item) => item.id)).toEqual([
      ids[4],
      ids[3],
    ]);
    expect((third.body.items as Found[]).map((item) => item.id)).toEqual([
      ids[0],
    ]);
  });
});

describe('틀린 검색어', () => {
  it.each([
    ['없다', {}],
    ['비었다', { q: '' }],
    ['한 글자다', { q: '가' }],
    ['한 글자인 낱말이 섞였다', { q: '주사위 가' }],
    ['낱말이 너무 많다', { q: '하나 두울 세엣 네엣 다섯 여섯' }],
    ['너무 길다', { q: '가'.repeat(51) }],
    ['여러 번 적었다', { q: ['주사위', '버그'] }],
  ])('검색어가 %s -> 400 이다', async (_name, params) => {
    const response = await search(params as Record<string, string | string[]>);

    expect(response.status).toBe(400);
    expect(response.body.errors).toHaveProperty('q');
  });

  it('NUL 이 든 검색어는 400 이다. DB 까지 가지 않는다', async () => {
    const response = await request(app.getHttpServer()).get(
      `${API}/posts?q=%EC%A3%BC%EC%82%AC%EC%9C%84%00`,
    );

    // DB 에 그대로 물으면 DB 가 오류를 낸다
    expect(response.status).toBe(400);
  });

  it('게시판 이름의 모양이 아니면 400 이다', async () => {
    const response = await search({ q: '주사위', board: "free'--" });

    expect(response.status).toBe(400);
    expect(response.body.errors).toHaveProperty('board');
  });

  it('모르는 값을 붙이면 400 이다', async () => {
    const response = await search({ q: '주사위', sort: 'old' });

    expect(response.status).toBe(400);
  });
});

describe('글 하나를 읽는 주소와 섞이지 않는다', () => {
  it('/posts/1 은 글을 읽고, /posts?q= 는 글을 찾는다', async () => {
    const id = await writtenId('주사위 이야기');

    const read = await request(app.getHttpServer()).get(`${API}/posts/${id}`);
    const found = await search({ q: '주사위' });

    expect(read.body).toHaveProperty('content');
    expect(found.body).toHaveProperty('items');
  });
});
