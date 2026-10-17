// board-server/src/auth/session-revocations.ts

/**
 * 인증 서버가 내주는 끊긴 세션의 목록을 받아 기억한다(#274). Nest 를 모른다. 결제 서버(internal/revocations)와 같은 규칙이다.
 *
 * 이 서버는 토큰의 서명과 만료만 보고 인증 서버에 묻지 않는다. 그래서 인증 서버에서 세션을 끊어도
 * (비밀번호 변경, 계정 정지 등) 그 사용자의 access 토큰은 만료(15분)까지 통했다.
 * 인증 서버가 끊긴 세션의 목록을 내주고, 이 서버가 REFRESH_INTERVAL_SECONDS 마다 받아 간다. 끊은 뒤 30초쯤이면 여기서도 막힌다.
 * 목록의 모양은 인증 서버 README 의 "다른 서버에서 토큰을 검증하는 방법" 5단계에 있다.
 *
 * 목록은 요청과 상관없이 따로 받는다(session-revocations.refresher.ts). 요청이 인증 서버를 기다리지 않는다.
 * 받지 못하면 마지막으로 받은 목록을 그대로 쓴다. 한 번도 받지 못했으면 아무 세션도 끊긴 것으로 보지 않는다.
 * 줄은 access 토큰의 수명이 지나면 어차피 무의미해지므로, 공개키(jwks.ts)와 달리 버리는 상한을 두지 않는다.
 */

import { createHash } from 'node:crypto';
import { Logger } from '@nestjs/common';
import { outgoingHeaders } from '../observability/request-context.js';

/** 목록을 다시 받는 간격(초). 인증 서버가 정한 값(refresh_interval_seconds)과 같다 */
export const REFRESH_INTERVAL_SECONDS = 30;
/** 인증 서버의 응답을 기다리는 시간(밀리초). 요청과 따로 받으므로 길어도 요청이 기다리지 않는다 */
export const FETCH_TIMEOUT_MS = 5000;
/**
 * 읽는 문서의 가장 큰 크기(바이트). 줄 하나가 100바이트쯤이라 15분 동안 끊긴 세션이 8만 개를 넘어도 들어간다.
 * 제한이 없으면 잘못된(또는 악의적인) 응답이 메모리를 끝없이 채운다
 */
export const MAX_DOCUMENT_BYTES = 8 * 1024 * 1024;
/** 로그에 적는 이 일의 이름과, 받지 못했을 때의 오류 코드(docs/observability.md) */
export const FETCH_OPERATION = 'auth.revocations_fetch';
export const FETCH_ERROR_CODE = 'auth.revocations_unavailable';

/** 목록의 사용자(sub 의 SHA-256, 소문자 16진수 64자)의 모양 */
const DIGEST = /^[0-9a-f]{64}$/;

/** 끊긴 세션들. 사용자(sub 의 digest)마다, 받아들이는 가장 낮은 세션 버전이다. */
export type RevocationList = ReadonlyMap<string, number>;
/** 목록을 받아 오는 함수. 받지 못하면 RevocationsFetchError 를 낸다. 테스트가 가짜를 꽂는다 */
export type LoadRevocations = () => Promise<RevocationList>;
/** 주소에서 응답을 받아 오는 함수. Node 의 fetch 와 모양이 같다 */
export type Fetcher = typeof fetch;

/** 목록을 받지 못했다. 글은 이유의 종류만 담는다. 주소를 담지 않는다. */
export class RevocationsFetchError extends Error {}

/** 아무 세션도 끊기지 않은 목록. 한 번도 받지 못했을 때의 목록이다 */
export const NO_REVOCATIONS: RevocationList = new Map();

/** 토큰의 sub 를 목록에 실린 모양(SHA-256 의 16진수 64자)으로 바꾼다. 인증 서버와 같은 식이다. */
export function subDigest(sub: string): string {
  return createHash('sha256').update(sub, 'utf8').digest('hex');
}

/** 그 사용자의 그 버전의 토큰이 끊긴 세션의 것인가. 목록에 있고 버전이 min_ver 보다 작으면 끊긴 것이다. */
export function isRevoked(
  list: RevocationList,
  sub: string,
  version: number,
): boolean {
  const minVersion = list.get(subDigest(sub));
  return minVersion !== undefined && version < minVersion;
}

/** 값이 이름과 값의 묶음(객체)인가. 배열과 null 은 아니다. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** 목록의 한 줄이 맞는 모양인가. digest 와, 0 이상의 정수인 min_ver 가 있어야 한다. */
function isEntry(
  entry: unknown,
): entry is { sub_sha256: string; min_ver: number } {
  return (
    isRecord(entry) &&
    typeof entry.sub_sha256 === 'string' &&
    DIGEST.test(entry.sub_sha256) &&
    Number.isSafeInteger(entry.min_ver) &&
    (entry.min_ver as number) >= 0
  );
}

/**
 * 문서를 읽어 목록으로 바꾼다. 한 줄이라도 모양이 틀리면 문서 전체를 받지 않는다(기억하던 목록을 쓴다).
 * 틀린 줄만 건너뛰면 그 사용자의 끊긴 세션이 조용히 통한다.
 */
export function parseRevocations(document: unknown): RevocationList {
  if (!isRecord(document) || !Array.isArray(document.revocations)) {
    throw new RevocationsFetchError('모양이 틀린 문서다');
  }
  const list = new Map<string, number>();
  for (const entry of document.revocations) {
    if (!isEntry(entry)) {
      throw new RevocationsFetchError('모양이 틀린 문서다');
    }
    list.set(entry.sub_sha256, entry.min_ver);
  }
  return list;
}

/** 응답의 본문을 제한만큼만 읽는다. 넘으면 RevocationsFetchError 다. 다 읽은 뒤에 재지 않는다. */
async function readLimited(response: Response, limit: number): Promise<string> {
  if (response.body === null) {
    return '';
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      return Buffer.concat(chunks).toString('utf8');
    }
    size += value.byteLength;
    if (size > limit) {
      await reader.cancel();
      throw new RevocationsFetchError('문서가 너무 크다');
    }
    chunks.push(value);
  }
}

/**
 * 주소에서 목록의 문서를 받아 온다. 어떤 이유로든 받지 못하면 RevocationsFetchError 를 낸다.
 *
 * 다른 주소로 가라는 응답(리다이렉트)은 따라가지 않는다. 적어 둔 주소가 내준 목록만 믿는다.
 */
export async function fetchRevocationsDocument(
  url: string,
  fetcher: Fetcher = fetch,
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetcher(url, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      redirect: 'error',
      // 우리 서버끼리의 호출이다. 추적을 이어 준다(저장소 루트의 docs/observability.md)
      headers: outgoingHeaders(),
    });
  } catch (error) {
    throw new RevocationsFetchError('연결하지 못했다', { cause: error });
  }
  if (!response.ok) {
    throw new RevocationsFetchError('상태 코드가 200 이 아니다');
  }
  const text = await readLimited(response, MAX_DOCUMENT_BYTES);
  try {
    return JSON.parse(text) as unknown;
  } catch (error) {
    throw new RevocationsFetchError('모양이 틀린 문서다', { cause: error });
  }
}

/** 인증 서버에서 목록을 받아 온다. 받지 못했거나 모양이 틀리면 RevocationsFetchError 를 낸다. */
export async function loadRevocations(
  url: string,
  fetcher: Fetcher = fetch,
): Promise<RevocationList> {
  return parseRevocations(await fetchRevocationsDocument(url, fetcher));
}

/**
 * 마지막으로 받은 목록을 기억한다. 앱 하나에 하나만 만들어 모든 요청이 함께 쓴다.
 *
 * 목록을 받아 오는 함수를 밖에서 받는다. 테스트가 인증 서버 없이 돌릴 수 있다.
 */
export class RevocationCache {
  private readonly logger = new Logger(RevocationCache.name);
  private list: RevocationList = NO_REVOCATIONS;

  constructor(private readonly load: LoadRevocations) {}

  /** 기억한 목록으로 그 토큰이 끊긴 세션의 것인지 본다. */
  revoked(sub: string, version: number): boolean {
    return isRevoked(this.list, sub, version);
  }

  /**
   * 목록을 한 번 받아 바꾼다. 받았으면 true 다.
   * 받지 못하면 기억하던 목록을 그대로 두고, 이유의 종류만 로그에 남긴다. 주소를 적지 않는다. 내부 주소가 로그에 남는다.
   */
  async refresh(): Promise<boolean> {
    try {
      this.list = await this.load();
      return true;
    } catch (error) {
      if (!(error instanceof RevocationsFetchError)) {
        throw error;
      }
      this.logger.warn({
        message: '끊긴 세션의 목록을 받지 못해 기억한 것을 쓴다',
        operation: FETCH_OPERATION,
        error_code: FETCH_ERROR_CODE,
        reason: error.message,
      });
      return false;
    }
  }
}
