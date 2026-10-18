// board-server/test/auth.e2e-spec.ts

/**
 * 토큰 검증을 앱을 통째로 만들어 본다. 인증 서버는 띄우지 않는다.
 * 테스트가 만든 키로 토큰을 서명하고, 그 공개키를 인증 서버가 내준 것처럼 앱에 꽂는다.
 *
 * 여기서 보는 것은 문지기가 앱에 실제로 걸려 있는가, 응답의 상태 코드와 머리말과 모양이 맞는가다.
 * 토큰이 틀리는 경우 하나하나는 src/auth/tokens.spec.ts 가 본다.
 */

import { createServer, Server } from 'node:http';
import { AddressInfo } from 'node:net';
import { Controller, Get, Logger, Module } from '@nestjs/common';
import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { JwksFetchError, LoadKeys } from '../src/auth/jwks.js';
import { Public } from '../src/auth/public.decorator.js';
import {
  loadRevocations,
  RevocationList,
  RevocationsFetchError,
  subDigest,
} from '../src/auth/session-revocations.js';
import { both, createTestApp, useKeys, useRevocations } from './app.js';
import { captureLogs } from './logs.js';
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
    expect(response.body).toEqual({ user_id: USER_ID, is_operator: false });
  });

  it('roles 에 operator 가 있으면 운영자라고 돌려준다', async () => {
    const response = await readMe(
      await signToken(key, { roles: ['operator'] }),
    );

    expect(response.status).toBe(200);
    expect(response.body.is_operator).toBe(true);
  });

  it.each([
    ['roles 가 없는 토큰', { roles: null }],
    ['roles 가 목록이 아닌 토큰', { roles: 'operator' }],
  ])('%s 은 받되 운영자가 아니다', async (_name, options) => {
    const response = await readMe(await signToken(key, options));

    expect(response.status).toBe(200);
    expect(response.body.is_operator).toBe(false);
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
    const logs = captureLogs(app);

    const response = await request(app.getHttpServer())
      .get(ME)
      .set('Authorization', `Bearer ${await signToken(key)}`);
    await app.close();

    // 401 이 아니다. 401 을 주면 클라이언트가 멀쩡한 사용자를 로그아웃시킨다
    expect(response.status).toBe(503);
    // 클라이언트의 잘못이 아니다. 서버의 잘못으로 로그에 남는다
    expect(logs.finishedWith(503)).toMatchObject([{ level: 'error' }]);
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

describe('끊긴 세션(#274)', () => {
  /** 인증 서버가 USER_ID 의 세션을 버전 2 부터만 받도록 끊은 목록 */
  const cut: RevocationList = new Map([[subDigest(USER_ID), 2]]);

  /** 토큰을 붙여 /me 를 부른다. */
  function readMe(app: NestExpressApplication, token: string) {
    return request(app.getHttpServer())
      .get(ME)
      .set('Authorization', `Bearer ${token}`);
  }

  it('끊기 전에 발급된 토큰은 401 이고, 다른 틀린 토큰과 응답이 같다', async () => {
    const app = await createTestApp(
      both(
        useKeys(() => publicKeys(key)),
        useRevocations(() => Promise.resolve(cut)),
      ),
    );

    const old = await readMe(app, await signToken(key, { version: 1 }));
    const renewed = await readMe(app, await signToken(key, { version: 2 }));
    await app.close();

    expect(old.status).toBe(401);
    expect(old.body).toEqual({ detail: '인증이 필요합니다.' });
    expect(old.headers['www-authenticate']).toBe('Bearer');
    // 다시 로그인해 받은 토큰(버전이 오른 것)은 통한다
    expect(renewed.status).toBe(200);
  });

  it('인증 서버가 HTTP 로 내준 목록을 받아 막는다', async () => {
    // 인증 서버 대신 목록만 내주는 작은 서버. 받아 오는 길(fetch, 크기 제한, 모양 검사)까지 실제로 지난다
    const document = JSON.stringify({
      revocations: [{ sub_sha256: subDigest(USER_ID), min_ver: 2 }],
      refresh_interval_seconds: 30,
    });
    const authServer: Server = createServer((_request, response) => {
      response.setHeader('Content-Type', 'application/json');
      response.end(document);
    });
    await new Promise<void>((resolve) =>
      authServer.listen(0, '127.0.0.1', resolve),
    );
    const { port } = authServer.address() as AddressInfo;
    const url = `http://127.0.0.1:${port}/api/v1/auth/session-revocations`;
    const app = await createTestApp(
      both(
        useKeys(() => publicKeys(key)),
        useRevocations(() => loadRevocations(url)),
      ),
    );

    // 앱이 뜰 때 받기 시작하지만 기다리지 않는다. 받을 때까지 기다린 뒤 부른다
    await vi.waitFor(async () => {
      const response = await readMe(app, await signToken(key, { version: 1 }));
      expect(response.status).toBe(401);
    });
    await app.close();
    await new Promise((resolve) => authServer.close(resolve));
  });

  it('다른 사용자의 토큰은 막지 않는다', async () => {
    const app = await createTestApp(
      both(
        useKeys(() => publicKeys(key)),
        useRevocations(() => Promise.resolve(cut)),
      ),
    );

    const response = await readMe(
      app,
      await signToken(key, {
        subject: '1b4e28ba-2fa1-11d2-883f-0016d3cca427',
        version: 0,
      }),
    );
    await app.close();

    expect(response.status).toBe(200);
  });

  it('목록을 받지 못해도 서버는 뜨고, 토큰을 막지 않는다. 받지 못한 것은 경고로 남는다', async () => {
    // 앱이 뜰 때 바로 한 번 받는다. 받지 못한 경고를 화면에 찍지 않고 모은다
    const warn = vi
      .spyOn(Logger.prototype, 'warn')
      .mockImplementation(() => undefined);
    const app = await createTestApp(
      both(
        useKeys(() => publicKeys(key)),
        useRevocations(() =>
          Promise.reject(new RevocationsFetchError('연결하지 못했다')),
        ),
      ),
    );

    const response = await readMe(app, await signToken(key, { version: 0 }));
    await app.close();
    vi.restoreAllMocks();

    expect(response.status).toBe(200);
    expect(warn).toHaveBeenCalledWith(
      expect.objectContaining({ error_code: 'auth.revocations_unavailable' }),
    );
  });
});
