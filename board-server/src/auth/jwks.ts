// board-server/src/auth/jwks.ts

/**
 * 인증 서버의 공개키(JWKS)를 가져오고 기억한다. Nest 를 모른다. 게임 서버(app/auth/jwks.py)와 같은 규칙이다.
 *
 * 토큰을 검증할 때마다 인증 서버에 묻지 않는다. 한 번 가져온 키를 기억해 두고 쓴다.
 * 인증 서버가 죽어 있어도, 기억한 키가 있으면 이미 로그인한 사용자의 요청을 계속 처리한다.
 *
 * 규칙은 넷이다.
 *   1. 기억한 지 JWKS_CACHE_SECONDS 가 지나면 다시 가져온다.
 *   2. 기억에 없는 키 ID(kid)가 오면 다시 가져온다. 인증 서버가 키를 바꾼 경우다.
 *   3. 다시 가져오기는 REFETCH_INTERVAL_SECONDS 에 한 번만 시도한다.
 *      가짜 kid 를 계속 보내 인증 서버에 요청이 몰리게 하는 것을 막고, 죽은 인증 서버를 요청마다 기다리지 않는다.
 *   4. 다시 가져오기에 실패하면 기억하던 키를 계속 쓴다.
 *
 * 서명을 다루는 일(키를 읽기, 서명을 확인하기)은 jose 라이브러리에 맡긴다. 기억하는 규칙만 여기서 정한다.
 * jose 에도 키를 기억하는 기능(createRemoteJWKSet)이 있지만 4번이 없다. 기억한 키가 낡으면 인증 서버가
 * 죽어 있을 때 토큰을 검증하지 못한다.
 */

import { Logger } from '@nestjs/common';
import { importJWK } from 'jose';
import { tracedFetch } from '../observability/http-spans.js';
import { outgoingHeaders } from '../observability/request-context.js';

/** 가져온 키를 기억하는 시간(초) */
export const JWKS_CACHE_SECONDS = 60 * 60;
/** 다시 가져오기를 시도하는 최소 간격(초) */
export const REFETCH_INTERVAL_SECONDS = 60;
/** 인증 서버의 응답을 기다리는 시간(밀리초). 이 시간 동안 요청이 멈춰 있으므로 짧게 잡는다 */
export const FETCH_TIMEOUT_MS = 5000;
/**
 * 이 서버가 받는 서명 방식. 하나만 적는다. 키도 이 방식으로 읽는다.
 * 토큰 머리말의 alg 를 그대로 믿으면, 서명이 없는 토큰(none)이나
 * 공개키를 비밀키처럼 써서 만든 토큰(HS256)이 통과한다
 */
export const ALGORITHM = 'RS256';

/** 이 서버가 받는 키의 종류. 서명 방식(RS256)에 맞는 것만 기억한다 */
const KEY_TYPE = 'RSA';

/** kid 로 찾는 공개키들. */
export type Keys = ReadonlyMap<string, CryptoKey>;
/** 키 목록을 가져오는 함수. 받지 못하면 JwksFetchError 를 낸다. 테스트가 가짜를 꽂는다 */
export type LoadKeys = () => Promise<Keys>;
/** 지금 시각(초)을 돌려주는 함수. 뒤로 가지 않는 시계여야 한다 */
export type Clock = () => number;
/** 주소에서 응답을 받아 오는 함수. Node 의 fetch 와 모양이 같다 */
export type Fetcher = typeof fetch;

/** 인증 서버에서 쓸 수 있는 키 목록을 받지 못했다. */
export class JwksFetchError extends Error {}

/** 기억한 키가 하나도 없고, 지금 가져올 수도 없다. 토큰이 맞는지 틀린지 알 수 없다. */
export class JwksUnavailableError extends Error {}

/** 키 목록은 있지만 그 안에 이 kid 가 없다. 이 서버가 믿는 키로 서명한 토큰이 아니다. */
export class UnknownKeyError extends Error {}

/** 값이 이름과 값의 묶음(객체)인가. 배열과 null 은 아니다. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** JWKS 의 한 칸이 이 서버가 받는 공개키의 모양인가. kid 가 있는 RSA 공개키만 받는다. */
function isUsableEntry(entry: unknown): entry is Record<string, unknown> {
  if (!isRecord(entry) || entry.kty !== KEY_TYPE) {
    return false;
  }
  // d 는 개인키에만 있는 값이다. 개인키가 실려 왔으면 쓰지 않는다
  return typeof entry.kid === 'string' && entry.kid !== '' && !('d' in entry);
}

/** JWKS 의 한 칸을 서명 검증용 키로 읽는다. 읽을 수 없으면 undefined 다. */
async function importEntry(
  entry: Record<string, unknown>,
): Promise<CryptoKey | undefined> {
  try {
    const key = await importJWK(entry, ALGORITHM);
    return key instanceof Uint8Array ? undefined : key;
  } catch {
    return undefined;
  }
}

/**
 * JWKS 문서에서 서명 검증에 쓸 키를 골라 kid 로 찾을 수 있게 담는다.
 *
 * kid 가 없는 키, RSA 가 아닌 키, 읽을 수 없는 키는 건너뛴다.
 * 하나가 이상하다고 전부를 버리면, 인증 서버가 새 종류의 키를 추가했을 때 검증이 통째로 멈춘다.
 * 쓸 수 있는 키가 하나도 없으면 JwksFetchError 를 낸다.
 */
export async function parseJwks(document: unknown): Promise<Keys> {
  if (!isRecord(document) || !Array.isArray(document.keys)) {
    throw new JwksFetchError('JWKS 형식이 아니다');
  }

  const keys = new Map<string, CryptoKey>();
  for (const entry of document.keys) {
    if (!isUsableEntry(entry)) {
      continue;
    }
    const key = await importEntry(entry);
    if (key !== undefined) {
      keys.set(entry.kid as string, key);
    }
  }

  if (keys.size === 0) {
    throw new JwksFetchError('쓸 수 있는 키가 없다');
  }
  return keys;
}

/** 오류의 종류(클래스 이름). 오류의 글은 쓰지 않는다. 주소가 들어 있을 수 있다. */
function errorName(error: unknown): string {
  return error instanceof Error ? error.constructor.name : typeof error;
}

/**
 * 주소에서 JWKS 문서를 받아 온다. 어떤 이유로든 받지 못하면 JwksFetchError 를 낸다.
 *
 * 다른 주소로 가라는 응답(리다이렉트)은 따라가지 않는다. 적어 둔 주소가 내준 키만 믿는다.
 * 요청 안에서 부르면 client span 을 건다(observability/http-spans.ts).
 */
export async function fetchJwksDocument(
  url: string,
  fetcher: Fetcher = tracedFetch,
): Promise<unknown> {
  try {
    const response = await fetcher(url, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      redirect: 'error',
      // 우리 서버끼리의 호출이다. 추적을 이어 준다(저장소 루트의 docs/observability.md)
      headers: outgoingHeaders(),
    });
    if (!response.ok) {
      throw new JwksFetchError(`HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    if (error instanceof JwksFetchError) {
      throw error;
    }
    throw new JwksFetchError(errorName(error), { cause: error });
  }
}

/** 인증 서버에서 키 목록을 가져온다. 받지 못했거나 쓸 키가 없으면 JwksFetchError 를 낸다. */
export async function loadKeys(
  url: string,
  fetcher: Fetcher = tracedFetch,
): Promise<Keys> {
  return parseJwks(await fetchJwksDocument(url, fetcher));
}

/** 서버가 켜진 뒤로 흐른 시간(초). 컴퓨터의 시각을 고쳐도 뒤로 가지 않는다. */
export function monotonicSeconds(): number {
  return performance.now() / 1000;
}

/**
 * 가져온 키를 기억한다. 앱 하나에 하나만 만들어 모든 요청이 함께 쓴다.
 *
 * 키를 가져오는 함수와 시계를 밖에서 받는다. 테스트가 인증 서버 없이, 한 시간을 기다리지 않고 돌릴 수 있다.
 */
export class JwksCache {
  private readonly logger = new Logger(JwksCache.name);
  private keys: Keys = new Map();
  private fetchedAt: number | undefined;
  private lastAttemptAt: number | undefined;
  /** 지금 가져오는 중인 작업. 여러 요청이 동시에 와도 하나만 가져오게 한다 */
  private refetching: Promise<void> | undefined;

  constructor(
    private readonly load: LoadKeys,
    private readonly clock: Clock = monotonicSeconds,
  ) {}

  /**
   * kid 에 해당하는 키를 돌려준다.
   *
   * 키 목록이 아예 없으면 JwksUnavailableError, 목록에 그 kid 가 없으면 UnknownKeyError 를 낸다.
   */
  async getKey(kid: string): Promise<CryptoKey> {
    if (this.needsRefetch(kid)) {
      await this.refetchOnce(kid);
    }

    if (this.keys.size === 0) {
      throw new JwksUnavailableError();
    }
    const key = this.keys.get(kid);
    if (key === undefined) {
      throw new UnknownKeyError();
    }
    return key;
  }

  /** 기억한 것으로는 부족한가. 기억 시간이 지났거나, 모르는 kid 다. */
  private needsRefetch(kid: string): boolean {
    return this.isExpired() || !this.keys.has(kid);
  }

  private isExpired(): boolean {
    if (this.fetchedAt === undefined) {
      return true;
    }
    return this.clock() - this.fetchedAt >= JWKS_CACHE_SECONDS;
  }

  /** 지금 다시 가져오기를 시도해도 되는가. 마지막 시도에서 간격이 지났는가. */
  private mayAttempt(): boolean {
    if (this.lastAttemptAt === undefined) {
      return true;
    }
    return this.clock() - this.lastAttemptAt >= REFETCH_INTERVAL_SECONDS;
  }

  /**
   * 여러 요청이 동시에 와도 한 번만 다시 가져온다.
   *
   * 먼저 온 요청이 가져오는 동안 나머지는 그 작업이 끝나기를 기다린다.
   * 기다리지 않고 지나가면, 아직 키가 도착하지 않아서 멀쩡한 토큰을 거부하게 된다.
   */
  private async refetchOnce(kid: string): Promise<void> {
    if (this.refetching !== undefined) {
      await this.refetching;
    }
    // 기다리는 동안 먼저 온 요청이 이미 가져왔을 수 있다. 다시 확인한다
    if (!this.needsRefetch(kid) || !this.mayAttempt()) {
      return;
    }
    this.refetching = this.refetch();
    try {
      await this.refetching;
    } finally {
      this.refetching = undefined;
    }
  }

  /** 키 목록을 다시 가져온다. 실패하면 기억하던 키를 그대로 둔다. */
  private async refetch(): Promise<void> {
    // 성공하든 실패하든 시도한 시각을 적는다. 실패한 직후에 또 시도하지 않는다
    this.lastAttemptAt = this.clock();
    try {
      this.keys = await this.load();
    } catch (error) {
      if (!(error instanceof JwksFetchError)) {
        throw error;
      }
      // 주소를 적지 않는다. 내부 주소가 로그에 남는다
      this.logger.warn(
        `JWKS 를 가져오지 못했다: ${error.message}. 기억한 키 ${this.keys.size}개를 계속 쓴다`,
      );
      return;
    }
    this.fetchedAt = this.clock();
  }
}
