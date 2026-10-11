// board-server/test/health.e2e-spec.ts

/**
 * 살아 있는지, 준비됐는지 확인하는 주소를 앱을 통째로 만들어 불러 본다.
 * 주소의 앞부분과 머리말, 상태 코드를 여기서 본다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { DatabaseHealth } from '../src/database/database.health.js';
import { createTestApp } from './app.js';

describe('살아 있는지 확인하는 주소', () => {
  let app: NestExpressApplication;

  beforeAll(async () => {
    app = await createTestApp();
  });

  afterAll(async () => {
    await app.close();
  });

  it('로그인 없이 200 과 ok 를 돌려준다', async () => {
    const response = await request(app.getHttpServer()).get('/health');

    expect(response.status).toBe(200);
    expect(response.body).toEqual({ status: 'ok' });
  });

  it('API 주소 밖에 있다', async () => {
    const response = await request(app.getHttpServer()).get(
      `/${API_PREFIX}/health`,
    );

    // 프록시와 관리 도구가 부르는 주소라 버전이 붙은 주소 아래에 두지 않는다
    expect(response.status).toBe(404);
  });

  it('무엇으로 만든 서버인지 머리말로 알리지 않는다', async () => {
    const response = await request(app.getHttpServer()).get('/health');

    expect(response.headers['x-powered-by']).toBeUndefined();
  });
});

describe('준비됐는지 확인하는 주소', () => {
  it('DB 에 닿으면 200 과 ok 를 돌려준다', async () => {
    const app = await createTestApp();

    const response = await request(app.getHttpServer()).get('/health/ready');
    await app.close();

    expect(response.status).toBe(200);
    expect(response.body).toEqual({ status: 'ok' });
  });

  it('API 주소 밖에 있다', async () => {
    const app = await createTestApp();

    const response = await request(app.getHttpServer()).get(
      `/${API_PREFIX}/health/ready`,
    );
    await app.close();

    expect(response.status).toBe(404);
  });

  it('DB 에 닿지 않으면 503 을 돌려주고, 까닭은 알리지 않는다', async () => {
    // DB 주소와 계정 이름이 든 오류. 드라이버가 내는 오류가 이렇게 생겼다
    const secret = 'password authentication failed for user "board"';
    const broken = { ping: () => Promise.reject(new Error(secret)) };
    const app = await createTestApp((builder) =>
      builder.overrideProvider(DatabaseHealth).useValue(broken),
    );

    const response = await request(app.getHttpServer()).get('/health/ready');
    await app.close();

    expect(response.status).toBe(503);
    expect(response.body).toEqual({ status: 'unavailable' });
    expect(response.text).not.toContain('board');
  });

  it('DB 에 닿지 않아도 살아 있다고는 답한다', async () => {
    const broken = { ping: () => Promise.reject(new Error('끊겼다')) };
    const app = await createTestApp((builder) =>
      builder.overrideProvider(DatabaseHealth).useValue(broken),
    );

    const response = await request(app.getHttpServer()).get('/health');
    await app.close();

    // 살아 있는지는 DB 를 보지 않는다. DB 가 느려졌다고 관리 도구가 서버를 재시작하면 안 된다
    expect(response.status).toBe(200);
  });
});
