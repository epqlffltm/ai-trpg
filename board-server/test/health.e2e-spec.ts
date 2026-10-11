// board-server/test/health.e2e-spec.ts

/**
 * 앱을 통째로 만들어 주소로 불러 본다. 네트워크의 포트를 열지 않고 앱에 요청을 바로 넘긴다(supertest).
 * 빠르고, 포트가 겹칠 일이 없다.
 *
 * 서버를 띄울 때와 같은 규칙을 건다(setupApp). 주소의 앞부분과 머리말을 여기서 본다.
 */

import { Test } from '@nestjs/testing';
import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { AppModule } from '../src/app.module.js';
import { API_PREFIX, setupApp } from '../src/app.setup.js';

describe('살아 있는지 확인하는 주소', () => {
  let app: NestExpressApplication;

  beforeAll(async () => {
    const module = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
    app = module.createNestApplication<NestExpressApplication>();
    setupApp(app);
    await app.init();
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
