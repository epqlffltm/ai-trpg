// board-server/test/boards.e2e-spec.ts

/**
 * 게시판 목록의 API 를 앱을 통째로 만들어 불러 본다. 실제 PostgreSQL 에서 돈다.
 * 게시판은 마이그레이션이 넣은 것이다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { createTestApp } from './app.js';

describe('게시판 목록', () => {
  let app: NestExpressApplication;

  beforeAll(async () => {
    app = await createTestApp();
  });

  afterAll(async () => {
    await app.close();
  });

  it('로그인 없이 게시판을 정해 둔 차례대로 돌려준다', async () => {
    const response = await request(app.getHttpServer()).get(
      `/${API_PREFIX}/boards`,
    );

    expect(response.status).toBe(200);
    expect(response.body).toEqual([
      {
        slug: 'notice',
        name: '공지사항',
        description: '운영자가 알리는 소식입니다.',
        write_policy: 'operator',
      },
      {
        slug: 'event',
        name: '이벤트',
        description: '진행 중인 이벤트와 그 결과를 알립니다.',
        write_policy: 'operator',
      },
      {
        slug: 'free',
        name: '자유 게시판',
        description: '자유롭게 이야기를 나누는 곳입니다.',
        write_policy: 'member',
      },
      {
        slug: 'scenario',
        name: '시나리오 이야기',
        description: '시나리오에 대한 감상과 이야기를 나누는 곳입니다.',
        write_policy: 'member',
      },
    ]);
  });
});
