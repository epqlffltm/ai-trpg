// board-server/src/auth/jwks.spec.ts

/**
 * 공개키를 가져오고 기억하는 규칙(jwks.ts)을 검증한다. 인증 서버를 띄우지 않는다.
 * 키를 가져오는 함수와 시계를 가짜로 꽂는다.
 */

import { Logger } from '@nestjs/common';
import {
  jwksDocument,
  makeSigningKey,
  publicKeys,
  SigningKey,
} from '../../test/tokens.js';
import {
  fetchJwksDocument,
  Fetcher,
  JWKS_CACHE_SECONDS,
  JwksCache,
  JwksFetchError,
  JwksUnavailableError,
  Keys,
  loadKeys,
  parseJwks,
  REFETCH_INTERVAL_SECONDS,
  UnknownKeyError,
} from './jwks.js';

/** 테스트가 마음대로 돌리는 시계. */
function makeClock(): { now: number; read: () => number } {
  const clock = { now: 1000, read: () => clock.now };
  return clock;
}

/** 정해 둔 응답을 돌려주는 가짜 fetch. */
function fetcherReturning(response: Response): Fetcher {
  return () => Promise.resolve(response);
}

/** JSON 응답을 만든다. */
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

let first: SigningKey;
let second: SigningKey;

beforeAll(async () => {
  first = await makeSigningKey('key-1');
  second = await makeSigningKey('key-2');
});

beforeEach(() => {
  vi.spyOn(Logger.prototype, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('parseJwks', () => {
  it('키를 kid 로 찾을 수 있게 담는다', async () => {
    const keys = await parseJwks(jwksDocument(first, second));

    expect([...keys.keys()]).toEqual(['key-1', 'key-2']);
    expect(keys.get('key-1')?.type).toBe('public');
  });

  it.each([null, 'keys', 42, [], {}, { keys: 'none' }, { keys: {} }])(
    'JWKS 의 모양이 아니면(%j) 받지 못한 것이다',
    async (document) => {
      await expect(parseJwks(document)).rejects.toThrow(JwksFetchError);
    },
  );

  it('쓸 수 있는 키가 하나도 없으면 받지 못한 것이다', async () => {
    await expect(parseJwks({ keys: [] })).rejects.toThrow(JwksFetchError);
  });

  it('쓸 수 없는 키는 건너뛰고 나머지를 담는다', async () => {
    const document = {
      keys: [
        null,
        'key',
        // kid 가 없다
        { ...first.jwk, kid: undefined },
        { ...first.jwk, kid: '' },
        // RSA 가 아니다
        { kty: 'EC', kid: 'ec-key', crv: 'P-256', x: 'x', y: 'y' },
        { kty: 'oct', kid: 'shared-secret', k: 'c2VjcmV0' },
        // 읽을 수 없다
        { kty: 'RSA', kid: 'broken' },
        second.jwk,
      ],
    };

    const keys = await parseJwks(document);

    expect([...keys.keys()]).toEqual(['key-2']);
  });

  it('개인키가 실려 오면 쓰지 않는다', async () => {
    const leaked = { ...first.jwk, d: 'private-part' };

    const keys = await parseJwks({ keys: [leaked, second.jwk] });

    expect([...keys.keys()]).toEqual(['key-2']);
  });
});

describe('fetchJwksDocument', () => {
  it('응답의 JSON 을 돌려준다', async () => {
    const document = jwksDocument(first);

    const fetched = await fetchJwksDocument(
      'http://auth/jwks',
      fetcherReturning(jsonResponse(document)),
    );

    expect(fetched).toEqual(document);
  });

  it('적어 둔 주소를 부르고, 기다리는 시간을 정하고, 다른 주소로 따라가지 않는다', async () => {
    const fetcher = vi.fn<Fetcher>(() =>
      Promise.resolve(jsonResponse(jwksDocument(first))),
    );

    await fetchJwksDocument('http://auth/jwks', fetcher);

    expect(fetcher).toHaveBeenCalledWith(
      'http://auth/jwks',
      expect.objectContaining({
        redirect: 'error',
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it.each([404, 500, 503])(
    '실패한 응답(%i)은 받지 못한 것이다',
    async (status) => {
      const fetcher = fetcherReturning(jsonResponse({}, status));

      await expect(
        fetchJwksDocument('http://auth/jwks', fetcher),
      ).rejects.toThrow(JwksFetchError);
    },
  );

  it('JSON 이 아닌 응답은 받지 못한 것이다', async () => {
    const fetcher = fetcherReturning(new Response('<html>'));

    await expect(
      fetchJwksDocument('http://auth/jwks', fetcher),
    ).rejects.toThrow(JwksFetchError);
  });

  it('닿지 못하면 받지 못한 것이고, 예외의 글에 주소를 싣지 않는다', async () => {
    const refused = new TypeError('fetch failed: http://internal-auth:8000');
    const fetcher: Fetcher = () => Promise.reject(refused);

    const failure = await fetchJwksDocument(
      'http://internal-auth:8000/jwks',
      fetcher,
    ).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(JwksFetchError);
    expect((failure as Error).message).toBe('TypeError');
  });
});

describe('loadKeys', () => {
  it('받아 온 문서에서 키를 담는다', async () => {
    const fetcher = fetcherReturning(jsonResponse(jwksDocument(first)));

    const keys = await loadKeys('http://auth/jwks', fetcher);

    expect([...keys.keys()]).toEqual(['key-1']);
  });
});

describe('JwksCache', () => {
  it('처음 물으면 가져와서 돌려준다', async () => {
    const load = vi.fn(() => publicKeys(first));
    const cache = new JwksCache(load, makeClock().read);

    const key = await cache.getKey('key-1');

    expect(key.type).toBe('public');
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('기억한 키는 다시 가져오지 않는다', async () => {
    const load = vi.fn(() => publicKeys(first));
    const clock = makeClock();
    const cache = new JwksCache(load, clock.read);
    await cache.getKey('key-1');

    clock.now += JWKS_CACHE_SECONDS - 1;
    await cache.getKey('key-1');

    expect(load).toHaveBeenCalledTimes(1);
  });

  it('기억한 지 오래되면 다시 가져온다', async () => {
    const load = vi.fn(() => publicKeys(first));
    const clock = makeClock();
    const cache = new JwksCache(load, clock.read);
    await cache.getKey('key-1');

    clock.now += JWKS_CACHE_SECONDS;
    await cache.getKey('key-1');

    expect(load).toHaveBeenCalledTimes(2);
  });

  it('모르는 kid 가 오면 다시 가져온다(키가 바뀐 경우)', async () => {
    const load = vi
      .fn<() => Promise<Keys>>()
      .mockImplementationOnce(() => publicKeys(first))
      .mockImplementationOnce(() => publicKeys(first, second));
    const clock = makeClock();
    const cache = new JwksCache(load, clock.read);
    await cache.getKey('key-1');

    clock.now += REFETCH_INTERVAL_SECONDS;
    const key = await cache.getKey('key-2');

    expect(key.type).toBe('public');
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('다시 가져와도 없는 kid 는 모르는 키다', async () => {
    const cache = new JwksCache(() => publicKeys(first), makeClock().read);

    await expect(cache.getKey('forged')).rejects.toThrow(UnknownKeyError);
  });

  it('모르는 kid 가 잇달아 와도 간격 안에서는 한 번만 가져온다', async () => {
    const load = vi.fn(() => publicKeys(first));
    const clock = makeClock();
    const cache = new JwksCache(load, clock.read);
    await cache.getKey('key-1');

    clock.now += REFETCH_INTERVAL_SECONDS;
    await cache.getKey('forged-1').catch(() => undefined);
    clock.now += REFETCH_INTERVAL_SECONDS - 1;
    await cache.getKey('forged-2').catch(() => undefined);
    await cache.getKey('forged-3').catch(() => undefined);

    // 처음 한 번, 그리고 간격이 지난 뒤 한 번
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('간격 안에서도 기억한 키는 돌려준다', async () => {
    const clock = makeClock();
    const cache = new JwksCache(() => publicKeys(first), clock.read);
    await cache.getKey('forged').catch(() => undefined);

    await expect(cache.getKey('key-1')).resolves.toBeDefined();
  });

  it('다시 가져오기에 실패하면 기억하던 키를 계속 쓴다', async () => {
    const load = vi
      .fn<() => Promise<Keys>>()
      .mockImplementationOnce(() => publicKeys(first))
      .mockRejectedValue(new JwksFetchError('HTTP 503'));
    const clock = makeClock();
    const cache = new JwksCache(load, clock.read);
    await cache.getKey('key-1');

    clock.now += JWKS_CACHE_SECONDS;

    await expect(cache.getKey('key-1')).resolves.toBeDefined();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('실패한 직후에는 다시 시도하지 않고, 간격이 지나면 시도한다', async () => {
    const load = vi
      .fn<() => Promise<Keys>>()
      .mockRejectedValueOnce(new JwksFetchError('TimeoutError'))
      .mockImplementation(() => publicKeys(first));
    const clock = makeClock();
    const cache = new JwksCache(load, clock.read);

    await expect(cache.getKey('key-1')).rejects.toThrow(JwksUnavailableError);
    await expect(cache.getKey('key-1')).rejects.toThrow(JwksUnavailableError);
    expect(load).toHaveBeenCalledTimes(1);

    clock.now += REFETCH_INTERVAL_SECONDS;

    await expect(cache.getKey('key-1')).resolves.toBeDefined();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('기억한 키가 없고 가져올 수도 없으면 확인할 수 없다고 한다', async () => {
    const cache = new JwksCache(
      () => Promise.reject(new JwksFetchError('TypeError')),
      makeClock().read,
    );

    // 모르는 키(토큰이 틀렸다)가 아니다. 맞는지 틀린지 알 수 없는 것이다
    await expect(cache.getKey('key-1')).rejects.toThrow(JwksUnavailableError);
  });

  it('여러 요청이 동시에 와도 한 번만 가져오고, 모두 키를 받는다', async () => {
    let release: (keys: Keys) => void = () => undefined;
    const load = vi.fn(
      () => new Promise<Keys>((resolve) => (release = resolve)),
    );
    const cache = new JwksCache(load, makeClock().read);

    const waiting = Promise.all([
      cache.getKey('key-1'),
      cache.getKey('key-1'),
      cache.getKey('key-1'),
    ]);
    await Promise.resolve();
    release(await publicKeys(first));

    await expect(waiting).resolves.toHaveLength(3);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('가져오지 못한 까닭을 로그에 남기되 주소는 남기지 않는다', async () => {
    const warn = vi.spyOn(Logger.prototype, 'warn');
    const cache = new JwksCache(
      () => Promise.reject(new JwksFetchError('HTTP 503')),
      makeClock().read,
    );

    await cache.getKey('key-1').catch(() => undefined);

    expect(warn).toHaveBeenCalledWith(expect.stringContaining('HTTP 503'));
    expect(warn).not.toHaveBeenCalledWith(expect.stringContaining('http://'));
  });

  it('키를 가져오는 함수의 뜻밖의 오류는 삼키지 않는다', async () => {
    const cache = new JwksCache(
      () => Promise.reject(new RangeError('버그')),
      makeClock().read,
    );

    await expect(cache.getKey('key-1')).rejects.toThrow(RangeError);
  });
});
