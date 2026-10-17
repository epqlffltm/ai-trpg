// board-server/src/auth/session-revocations.spec.ts

/**
 * 끊긴 세션의 목록을 받고 기억하는 것(session-revocations.ts)과, 정해 둔 간격마다 받는 것(session-revocations.refresher.ts)을 검증한다.
 * 인증 서버는 띄우지 않는다. 응답은 가짜 fetch 가 만든다.
 */

import { Logger } from '@nestjs/common';
import { RevocationsRefresher } from './session-revocations.refresher.js';
import {
  Fetcher,
  fetchRevocationsDocument,
  isRevoked,
  loadRevocations,
  MAX_DOCUMENT_BYTES,
  NO_REVOCATIONS,
  parseRevocations,
  REFRESH_INTERVAL_SECONDS,
  RevocationCache,
  RevocationList,
  RevocationsFetchError,
  subDigest,
} from './session-revocations.js';

// 인증 서버의 테스트(accounts/tests/test_session_revocations.py), 결제 서버의 테스트와 같은 예시다. 세 서버가 같은 값을 계산해야 한다
const EXAMPLE_SUB = '0d3f7a52-6f0a-4c1e-9d55-2b8a4c1f7e90';
const EXAMPLE_DIGEST =
  '08f6625d1aecc747bd6122bbf85ef9fb3fc0f25f7986169f057f12639fe6c0ed';
const URL = 'http://auth.internal:8000/api/v1/auth/session-revocations';

/** 늘 같은 응답을 내는 가짜 fetch. */
function fetcherReturning(response: Response): Fetcher {
  return () => Promise.resolve(response);
}

/** JSON 본문의 응답. */
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

/** 인증 서버가 내주는 문서의 모양. */
function documentOf(...entries: [string, number][]): unknown {
  return {
    revocations: entries.map(([digest, minVer]) => ({
      sub_sha256: digest,
      min_ver: minVer,
    })),
    refresh_interval_seconds: 30,
  };
}

/** 정해 둔 목록을 내주는 가짜 함수. 바꿀 수 있다. */
function loaderOf(list: RevocationList) {
  let next: RevocationList | Error = list;
  const load = vi.fn(() =>
    next instanceof Error ? Promise.reject(next) : Promise.resolve(next),
  );
  return {
    load,
    answer: (value: RevocationList | Error) => {
      next = value;
    },
  };
}

beforeEach(() => {
  // 받지 못한 것은 경고로 남는다. 테스트가 일부러 만든 경고를 화면에 찍지 않는다
  vi.spyOn(Logger.prototype, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('subDigest', () => {
  it('인증 서버와 같은 값을 계산한다', () => {
    expect(subDigest(EXAMPLE_SUB)).toBe(EXAMPLE_DIGEST);
  });
});

describe('isRevoked', () => {
  const list: RevocationList = new Map([[EXAMPLE_DIGEST, 3]]);

  it.each([
    [0, true],
    [2, true],
    [3, false],
    [4, false],
  ])(
    '목록의 버전(3)보다 낮은 토큰만 끊긴 것이다: ver %d',
    (version, revoked) => {
      expect(isRevoked(list, EXAMPLE_SUB, version)).toBe(revoked);
    },
  );

  it('목록에 없는 사용자는 끊기지 않았다', () => {
    expect(isRevoked(list, '1b4e28ba-2fa1-11d2-883f-0016d3cca427', 0)).toBe(
      false,
    );
  });
});

describe('parseRevocations', () => {
  it('문서를 목록으로 읽는다', () => {
    expect(parseRevocations(documentOf([EXAMPLE_DIGEST, 3]))).toEqual(
      new Map([[EXAMPLE_DIGEST, 3]]),
    );
    expect(parseRevocations({ revocations: [] }).size).toBe(0);
  });

  // 한 줄이라도 틀리면 문서 전체를 받지 않는다. 틀린 줄만 건너뛰면 그 사용자의 끊긴 세션이 조용히 통한다
  it.each([
    ['문서가 객체가 아니다', []],
    ['목록이 없다', {}],
    ['해시가 대문자다', documentOf([EXAMPLE_DIGEST.toUpperCase(), 1])],
    ['해시가 짧다', documentOf(['08f6', 1])],
    ['버전이 없다', { revocations: [{ sub_sha256: EXAMPLE_DIGEST }] }],
    ['버전이 음수다', documentOf([EXAMPLE_DIGEST, -1])],
    [
      '버전이 숫자가 아니다',
      { revocations: [{ sub_sha256: EXAMPLE_DIGEST, min_ver: '3' }] },
    ],
    ['줄이 객체가 아니다', { revocations: ['x'] }],
  ])('모양이 틀린 문서를 받지 않는다: %s', (_name, document) => {
    expect(() => parseRevocations(document)).toThrow(RevocationsFetchError);
  });
});

describe('fetchRevocationsDocument', () => {
  it('정해 둔 주소에서, 다른 주소로 가라는 응답을 따라가지 않고 받는다', async () => {
    const fetcher = vi.fn<Fetcher>(() =>
      Promise.resolve(jsonResponse(documentOf())),
    );

    await fetchRevocationsDocument(URL, fetcher);

    expect(fetcher).toHaveBeenCalledWith(
      URL,
      expect.objectContaining({ redirect: 'error' }),
    );
  });

  it.each([
    [
      '상태 코드가 200 이 아니다',
      () => fetcherReturning(jsonResponse({}, 503)),
    ],
    ['모양이 틀린 문서다', () => fetcherReturning(new Response('<html>'))],
    [
      '연결하지 못했다',
      (): Fetcher => () => Promise.reject(new TypeError('fetch failed')),
    ],
  ])('받지 못하면 그 종류를 알린다: %s', async (reason, makeFetcher) => {
    await expect(fetchRevocationsDocument(URL, makeFetcher())).rejects.toThrow(
      new RevocationsFetchError(reason),
    );
  });

  it('너무 큰 문서는 끝까지 읽지 않고 거부한다', async () => {
    const huge = new Response(new Uint8Array(MAX_DOCUMENT_BYTES + 1).fill(32));

    await expect(
      fetchRevocationsDocument(URL, fetcherReturning(huge)),
    ).rejects.toThrow(new RevocationsFetchError('문서가 너무 크다'));
  });

  it('본문이 없으면 모양이 틀린 문서다', async () => {
    const empty = new Response(null, { status: 200 });

    await expect(
      fetchRevocationsDocument(URL, fetcherReturning(empty)),
    ).rejects.toThrow(new RevocationsFetchError('모양이 틀린 문서다'));
  });
});

describe('loadRevocations', () => {
  it('받아서 목록으로 읽는다', async () => {
    const list = await loadRevocations(
      URL,
      fetcherReturning(jsonResponse(documentOf([EXAMPLE_DIGEST, 2]))),
    );

    expect(list.get(EXAMPLE_DIGEST)).toBe(2);
  });
});

describe('RevocationCache', () => {
  it('목록을 받기 전에는 아무 세션도 끊긴 것으로 보지 않는다', () => {
    const cache = new RevocationCache(loaderOf(NO_REVOCATIONS).load);

    expect(cache.revoked(EXAMPLE_SUB, 0)).toBe(false);
  });

  it('받은 목록으로 본다. 새 목록에서 빠진 줄은 여기서도 빠진다', async () => {
    const loader = loaderOf(new Map([[EXAMPLE_DIGEST, 1]]));
    const cache = new RevocationCache(loader.load);

    expect(await cache.refresh()).toBe(true);
    expect(cache.revoked(EXAMPLE_SUB, 0)).toBe(true);

    loader.answer(NO_REVOCATIONS);
    await cache.refresh();
    expect(cache.revoked(EXAMPLE_SUB, 0)).toBe(false);
  });

  it('받지 못하면 기억하던 목록을 쓰고, 이유의 종류만 남긴다. 주소는 남기지 않는다', async () => {
    const warn = vi.spyOn(Logger.prototype, 'warn');
    const loader = loaderOf(new Map([[EXAMPLE_DIGEST, 1]]));
    const cache = new RevocationCache(loader.load);
    await cache.refresh();

    loader.answer(new RevocationsFetchError('연결하지 못했다'));
    expect(await cache.refresh()).toBe(false);

    expect(cache.revoked(EXAMPLE_SUB, 0)).toBe(true);
    expect(warn).toHaveBeenCalledWith({
      message: '끊긴 세션의 목록을 받지 못해 기억한 것을 쓴다',
      operation: 'auth.revocations_fetch',
      error_code: 'auth.revocations_unavailable',
      reason: '연결하지 못했다',
    });
    expect(JSON.stringify(warn.mock.calls)).not.toContain('auth.internal');
  });

  it('받는 일과 상관없는 예외(코드의 버그)는 감추지 않는다', async () => {
    const loader = loaderOf(NO_REVOCATIONS);
    loader.answer(new TypeError('bug'));
    const cache = new RevocationCache(loader.load);

    await expect(cache.refresh()).rejects.toThrow(TypeError);
  });
});

describe('RevocationsRefresher', () => {
  it('앱이 뜨면 바로 받고, 간격마다 다시 받고, 닫히면 멈춘다', async () => {
    vi.useFakeTimers();
    const loader = loaderOf(NO_REVOCATIONS);
    const refresher = new RevocationsRefresher(
      new RevocationCache(loader.load),
    );

    refresher.onApplicationBootstrap();
    expect(loader.load).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_SECONDS * 1000);
    expect(loader.load).toHaveBeenCalledTimes(2);

    refresher.onModuleDestroy();
    await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_SECONDS * 1000 * 3);
    expect(loader.load).toHaveBeenCalledTimes(2);
  });

  it('받지 못해도, 예상하지 못한 오류가 나도 멈추지 않는다', async () => {
    vi.useFakeTimers();
    const error = vi
      .spyOn(Logger.prototype, 'error')
      .mockImplementation(() => undefined);
    const loader = loaderOf(NO_REVOCATIONS);
    loader.answer(new TypeError('bug'));
    const refresher = new RevocationsRefresher(
      new RevocationCache(loader.load),
    );

    refresher.onApplicationBootstrap();
    await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_SECONDS * 1000);
    refresher.onModuleDestroy();

    expect(loader.load).toHaveBeenCalledTimes(2);
    expect(error).toHaveBeenCalledWith(
      expect.objectContaining({
        error_code: 'internal.error',
        error_type: 'TypeError',
      }),
      expect.any(String),
    );
  });
});
