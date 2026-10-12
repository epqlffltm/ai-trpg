// board-server/test/search-timeout.e2e-spec.ts

/**
 * 검색이 정해 둔 시간을 넘기면 멈추는지 본다. 실제 PostgreSQL 의 테스트용 스키마에서 돈다.
 *
 * 서버는 3초를 준다. 여기서는 0.1초를 주고, 그 안에 끝나지 못할 만큼 글을 넣는다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { DataSource } from 'typeorm';
import { API_PREFIX } from '../src/app.setup.js';
import { SEARCH_TIMEOUT } from '../src/posts/posts-search.service.js';
import { createTestApp } from './app.js';
import { clearData, insertManyPosts } from './data.js';
import { CapturedLogs, captureLogs } from './logs.js';

const API = `/${API_PREFIX}`;
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
/** 이 테스트의 앱이 검색에 주는 시간(천분의 1초) */
const TIMEOUT_MS = 100;
/** 훑는 데 TIMEOUT_MS 보다 훨씬 오래 걸리는 글의 수. 글마다 본문이 2,000자쯤이다 */
const MANY_POSTS = 20_000;

let app: NestExpressApplication;
/** 서버의 로그. 멈춘 검색(503)의 오류 줄을 화면 대신 여기에 모은다 */
let logs: CapturedLogs;

beforeAll(async () => {
  app = await createTestApp((builder) =>
    builder.overrideProvider(SEARCH_TIMEOUT).useValue(TIMEOUT_MS),
  );
  logs = captureLogs(app);
});

afterAll(async () => {
  await clearData(app);
  await app.close();
});

beforeEach(async () => {
  await clearData(app);
  logs.lines.length = 0;
});

/** 글을 검색한다. */
function search(): request.Test {
  return request(app.getHttpServer())
    .get(`${API}/posts`)
    .query({ q: '없는낱말' });
}

describe('검색의 시간 제한', () => {
  it('정해 둔 시간을 넘기면 503 이고, 까닭을 싣지 않는다', async () => {
    await insertManyPosts(app, MANY_POSTS, WRITER);

    const response = await search();

    expect(response.status).toBe(503);
    expect(response.body).toEqual({
      detail: '검색이 오래 걸려 멈췄습니다. 검색어를 바꿔 다시 시도해 주세요.',
    });
    // DB 의 오류(쿼리, statement timeout)는 응답에 나가지 않는다
    expect(response.text).not.toContain('statement');
    expect(response.text).not.toContain('SELECT');
  });

  it('멈춘 검색은 서버의 잘못으로 로그에 남는다(error). 쿼리는 싣지 않는다', async () => {
    await insertManyPosts(app, MANY_POSTS, WRITER);

    await search();

    const [line] = logs.finishedWith(503);
    expect(line).toMatchObject({ level: 'error', result: 'server_error' });
    expect(logs.lines.join('\n')).not.toContain('SELECT');
  });

  it('멈춘 뒤에도 서버는 다른 요청에 답한다', async () => {
    await insertManyPosts(app, MANY_POSTS, WRITER);
    await search();

    const listing = await request(app.getHttpServer()).get(
      `${API}/boards/free/posts`,
    );

    expect(listing.status).toBe(200);
    expect(listing.body.total).toBe(MANY_POSTS);
  });

  it('시간 제한은 검색의 쿼리에만 걸린다. 연결에 남지 않는다', async () => {
    // 글이 없어서 검색이 제때 끝난다
    expect((await search()).status).toBe(200);

    // 제한이 연결에 남았으면, 풀에 돌아간 그 연결을 받은 쿼리가 TIMEOUT_MS 에서 멈춘다.
    // 풀의 연결을 모두 쓰도록 한꺼번에 여럿을 보낸다
    const dataSource = app.get(DataSource);
    const waits = Array.from({ length: 10 }, () =>
      dataSource.query(`SELECT pg_sleep(${(TIMEOUT_MS * 3) / 1000})`),
    );

    await expect(Promise.all(waits)).resolves.toHaveLength(10);
  });
});
