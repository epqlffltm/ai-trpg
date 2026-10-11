// board-server/test/errors.e2e-spec.ts

/**
 * 오류 응답의 모양을 앱을 통째로 만들어 본다. 예외를 응답으로 바꾸는 필터와 입력을 검사하는 파이프가
 * 앱에 실제로 걸려 있는지 확인한다. 문장을 만드는 규칙은 src/errors 의 테스트가 본다.
 */

import { Controller, Get, Logger, Module } from '@nestjs/common';
import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { Public } from '../src/auth/public.decorator.js';
import { createTestApp, useKeys } from './app.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

/** 코드를 잘못 짠 컨트롤러의 흉내. 뜻밖의 예외를 낸다. */
@Public()
@Controller('broken')
class BrokenController {
  @Get()
  read(): never {
    // DB 드라이버가 내는 오류의 흉내. 응답에 실리면 안 되는 글이다
    throw new Error('relation "board_test.posts" does not exist');
  }
}

@Module({ controllers: [BrokenController] })
class ProbeModule {}

describe('오류 응답', () => {
  let app: NestExpressApplication;
  let key: SigningKey;

  beforeAll(async () => {
    key = await makeSigningKey('key-1');
    app = await createTestApp(
      useKeys(() => publicKeys(key)),
      [ProbeModule],
    );
  });

  afterAll(async () => {
    await app.close();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('없는 주소는 404 이고, 받은 주소를 되돌려 적지 않는다', async () => {
    const response = await request(app.getHttpServer()).get(
      `/${API_PREFIX}/no-such-api`,
    );

    expect(response.status).toBe(404);
    expect(response.body).toEqual({ detail: '찾을 수 없습니다.' });
  });

  it('깨진 JSON 은 400 이고, 파서의 글을 내보내지 않는다', async () => {
    const response = await request(app.getHttpServer())
      .post(`/${API_PREFIX}/boards/free/posts`)
      .set('Authorization', `Bearer ${await signToken(key)}`)
      .set('Content-Type', 'application/json')
      .send('{"title": "첫 글", ');

    expect(response.status).toBe(400);
    expect(response.body).toEqual({ detail: '요청이 올바르지 않습니다.' });
  });

  it('입력이 틀리면 400 이고, 어느 칸이 왜 틀렸는지 알린다', async () => {
    const response = await request(app.getHttpServer())
      .post(`/${API_PREFIX}/boards/free/posts`)
      .set('Authorization', `Bearer ${await signToken(key)}`)
      .send({ title: '   ', content: '본문' });

    expect(response.status).toBe(400);
    expect(response.body).toEqual({
      detail: '입력이 올바르지 않습니다.',
      errors: { title: ['제목을 적어야 합니다.'] },
    });
  });

  it('뜻밖의 예외는 500 이고, 예외의 글을 내보내지 않는다', async () => {
    const error = vi
      .spyOn(Logger.prototype, 'error')
      .mockImplementation(() => undefined);

    const response = await request(app.getHttpServer()).get(
      `/${API_PREFIX}/broken`,
    );

    expect(response.status).toBe(500);
    expect(response.body).toEqual({ detail: '서버에서 오류가 났습니다.' });
    expect(response.text).not.toContain('board_test');
    // 응답에는 싣지 않지만 로그에는 남긴다
    expect(error).toHaveBeenCalledWith(
      'relation "board_test.posts" does not exist',
      expect.any(String),
    );
  });
});
