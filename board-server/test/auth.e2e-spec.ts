// board-server/test/auth.e2e-spec.ts

/**
 * 토큰 검증을 앱을 통째로 만들어 본다. 인증 서버는 띄우지 않는다.
 * 테스트가 만든 키로 토큰을 서명하고, 그 공개키를 인증 서버가 내준 것처럼 앱에 꽂는다.
 *
 * 여기서 보는 것은 문지기가 앱에 실제로 걸려 있는가, 응답의 상태 코드와 머리말과 모양이 맞는가다.
 * 토큰이 틀리는 경우 하나하나는 src/auth/tokens.spec.ts 가 본다.
 */

import { Controller, Get, Logger, Module } from '@nestjs/common';
import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { JwksFetchError, LoadKeys } from '../src/auth/jwks.js';
import { Public } from '../src/auth/public.decorator.js';
import { createTestApp, useKeys } from './app.js';
import {
  forgeToken,
  makeSigningKey,
  publicKeys,
  SigningKey,
  signToken,
  USER_ID,
  validClaims,
} from './tokens.js';

const ME = `/${API_PREFIX}/me`;

/** 표시를 하나도 붙이지 않은 컨트롤러. 새로 만든 API 가 기본으로 닫혀 있는지 본다. */
@Controller('unmarked')
class UnmarkedController {
  @Get()
  read(): { opened: boolean } {
    return { opened: true };
  }
}

/** 열어 둔다고 표시한 컨트롤러. */
@Public()
@Controller('opened')
class OpenedController {
  @Get()
  read(): { opened: boolean } {
    return { opened: true };
  }
}

@Module({ controllers: [UnmarkedController, OpenedController] })
class ProbeModule {}

let key: SigningKey;
let stranger: SigningKey;

beforeAll(async () => {
  key = await makeSigningKey('key-1');
  // 인증 서버의 것이 아닌 키. kid 만 같다
  stranger = await makeSigningKey('key-1');
});

/** 인증 서버가 key 의 공개키를 내주는 것처럼 꾸민 앱을 만든다. */
function createAppWithKeys(): Promise<NestExpressApplication> {
  return createTestApp(useKeys(() => publicKeys(key)));
}

describe('로그인이 필요한 API', () => {
  let app: NestExpressApplication;

  beforeAll(async () => {
    app = await createAppWithKeys();
  });

  afterAll(async () => {
    await app.close();
  });

  /** 토큰을 붙여 /me 를 부른다. */
  function readMe(token: string) {
    return request(app.getHttpServer())
      .get(ME)
      .set('Authorization', `Bearer ${token}`);
  }

  it('맞는 토큰이면 200 과 주인의 ID 를 돌려준다', async () => {
    const response = await readMe(await signToken(key));

    expect(response.status).toBe(200);
    expect(response.body).toEqual({ user_id: USER_ID });
  });

  it('토큰이 없으면 401 이고, 어떤 방식으로 인증하는지 머리말로 알린다', async () => {
    const response = await request(app.getHttpServer()).get(ME);

    expect(response.status).toBe(401);
    expect(response.headers['www-authenticate']).toBe('Bearer');
    expect(response.body).toEqual({ detail: '인증이 필요합니다.' });
  });

  it('Bearer 가 아닌 방식이면 401 이다', async () => {
    const response = await request(app.getHttpServer())
      .get(ME)
      .set('Authorization', 'Basic dXNlcjpwYXNz');

    expect(response.status).toBe(401);
  });

  it.each([
    ['만료된 토큰', { expiresInSeconds: -60 }],
    ['다른 서버에만 쓰라고 발급된 토큰', { audience: ['ai-trpg-game'] }],
    ['다른 곳이 발급한 토큰', { issuer: 'someone-else' }],
    ['refresh 토큰', { tokenType: 'refresh' }],
    ['모르는 kid 의 토큰', { kid: 'forged' }],
    ['주인의 ID 가 UUID 가 아닌 토큰', { subject: '42' }],
  ])('%s 은 401 이고, 까닭을 알리지 않는다', async (_name, options) => {
    const response = await readMe(await signToken(key, options));

    expect(response.status).toBe(401);
    // 어느 경우든 응답이 똑같다. 무엇이 틀렸는지 응답으로는 가릴 수 없다
    expect(response.body).toEqual({ detail: '인증이 필요합니다.' });
    expect(response.headers['www-authenticate']).toBe('Bearer');
  });

  it('kid 만 같은 다른 키로 서명한 토큰은 401 이다', async () => {
    const response = await readMe(await signToken(stranger));

    expect(response.status).toBe(401);
  });

  it('서명이 없는 토큰(none)은 401 이다', async () => {
    const token = forgeToken({ alg: 'none', kid: 'key-1' }, validClaims());

    const response = await readMe(token);

    expect(response.status).toBe(401);
  });

  it('토큰의 모양이 아닌 글자는 401 이다', async () => {
    const response = await readMe('not-a-token');

    expect(response.status).toBe(401);
  });

  it('살아 있는지와 준비됐는지는 토큰 없이도 답한다', async () => {
    const health = await request(app.getHttpServer()).get('/health');
    const ready = await request(app.getHttpServer()).get('/health/ready');

    expect(health.status).toBe(200);
    expect(ready.status).toBe(200);
  });

  it('없는 주소는 401 이 아니라 404 다', async () => {
    const response = await request(app.getHttpServer()).get(
      `/${API_PREFIX}/no-such-api`,
    );

    expect(response.status).toBe(404);
  });
});

describe('새로 만든 API', () => {
  let app: NestExpressApplication;

  beforeAll(async () => {
    app = await createTestApp(
      useKeys(() => publicKeys(key)),
      [ProbeModule],
    );
  });

  afterAll(async () => {
    await app.close();
  });

  it('표시를 붙이지 않으면 닫혀 있다', async () => {
    const response = await request(app.getHttpServer()).get(
      `/${API_PREFIX}/unmarked`,
    );

    // 열어 두는 표시를 빠뜨린 API 가 열려 있으면 안 된다
    expect(response.status).toBe(401);
  });

  it('표시를 붙이지 않아도 토큰이 맞으면 들어간다', async () => {
    const response = await request(app.getHttpServer())
      .get(`/${API_PREFIX}/unmarked`)
      .set('Authorization', `Bearer ${await signToken(key)}`);

    expect(response.status).toBe(200);
  });

  it('열어 둔다고 표시하면 토큰 없이 들어간다', async () => {
    const response = await request(app.getHttpServer()).get(
      `/${API_PREFIX}/opened`,
    );

    expect(response.status).toBe(200);
    expect(response.body).toEqual({ opened: true });
  });
});

describe('인증 서버에 닿지 않을 때', () => {
  beforeEach(() => {
    vi.spyOn(Logger.prototype, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('키를 한 번도 받지 못했으면 503 이고, 언제 다시 해 볼지 알린다', async () => {
    const down: LoadKeys = () =>
      Promise.reject(new JwksFetchError('TypeError'));
    const app = await createTestApp(useKeys(down));

    const response = await request(app.getHttpServer())
      .get(ME)
      .set('Authorization', `Bearer ${await signToken(key)}`);
    await app.close();

    // 401 이 아니다. 401 을 주면 클라이언트가 멀쩡한 사용자를 로그아웃시킨다
    expect(response.status).toBe(503);
    expect(response.headers['retry-after']).toBe('60');
    expect(response.body).toEqual({
      detail: '지금은 인증을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.',
    });
  });

  it('토큰이 없는 요청은 그래도 401 이다', async () => {
    const down: LoadKeys = () =>
      Promise.reject(new JwksFetchError('TypeError'));
    const app = await createTestApp(useKeys(down));

    const response = await request(app.getHttpServer()).get(ME);
    await app.close();

    expect(response.status).toBe(401);
  });

  it('한 번 받은 키는 인증 서버가 죽은 뒤에도 쓴다', async () => {
    let alive = true;
    const flaky: LoadKeys = () =>
      alive ? publicKeys(key) : Promise.reject(new JwksFetchError('TypeError'));
    const app = await createTestApp(useKeys(flaky));
    const token = await signToken(key);
    await request(app.getHttpServer())
      .get(ME)
      .set('Authorization', `Bearer ${token}`);

    alive = false;
    const response = await request(app.getHttpServer())
      .get(ME)
      .set('Authorization', `Bearer ${token}`);
    await app.close();

    expect(response.status).toBe(200);
  });

  it('서버는 인증 서버 없이도 뜨고, 로그인이 필요 없는 API 는 답한다', async () => {
    // 기본 앱은 키를 받지 못한다(test/app.ts)
    const app = await createTestApp();

    const response = await request(app.getHttpServer()).get('/health/ready');
    await app.close();

    expect(response.status).toBe(200);
  });
});
