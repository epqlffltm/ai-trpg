// board-server/src/auth/tokens.ts

/**
 * 인증 서버가 발급한 access 토큰을 검증한다. Nest 를 모른다. 게임 서버(app/auth/tokens.py)와 같은 규칙이다.
 *
 * 인증 서버의 DB 를 보지 않는다. 공개키로 서명을 확인하고, 토큰 안에 적힌 값만 본다.
 * 그래서 인증 서버에서 로그아웃하거나 계정이 정지돼도, 이미 발급된 access 토큰은 만료될 때까지 통한다.
 * access 토큰의 수명을 짧게(15분) 잡는 이유다.
 *
 * 확인하는 것:
 *   - 서명 방식이 RS256 인가. 토큰이 스스로 적어 온 방식을 믿지 않는다.
 *   - 인증 서버의 키로 서명됐는가.
 *   - 만료되지 않았는가(exp).
 *   - 인증 서버가 발급했는가(iss).
 *   - 이 서버에 쓰라고 발급됐는가(aud). 토큰에는 대상의 목록이 실리고, 그 안에 이 서버의 이름이 있어야 한다.
 *   - access 토큰인가. refresh 토큰도 같은 키로 서명되므로 종류를 따로 본다.
 *   - 세션 버전(ver)이 0 이상의 정수인가. 없으면 0 으로 본다(인증 서버 README 의 약속).
 *
 * 끊긴 세션의 것인지(ver 가 끊긴 세션 목록의 것보다 낮은가)는 여기서 보지 않는다. 목록을 기억하는 쪽(token-verifier.ts)이 본다.
 */

import { decodeProtectedHeader, errors, JWTPayload, jwtVerify } from 'jose';
import { readNickname } from '../authors/nickname.js';
import { Environment } from '../config/environment.js';
import { ALGORITHM, JwksCache, UnknownKeyError } from './jwks.js';

/** 토큰에 반드시 있어야 하는 값. 없으면 확인을 건너뛰지 않고 거부한다 */
const REQUIRED_CLAIMS = ['exp', 'iss', 'aud', 'sub'];
/** access 토큰의 token_type 값. 인증 서버(simplejwt)가 넣는다 */
const ACCESS_TOKEN_TYPE = 'access';
/** 세션 버전이 없는 토큰의 버전. 인증 서버가 버전을 싣기 전에 발급한 토큰이다 */
const DEFAULT_SESSION_VERSION = 0;
/**
 * 서버끼리 시계가 조금 어긋나는 것을 봐주는 시간(초).
 * 0 이면 인증 서버의 시계가 1초만 빨라도 방금 발급한 토큰이 "아직 유효하지 않다"로 거부된다
 */
export const CLOCK_SKEW_SECONDS = 10;
/** 사용자 ID 의 모양. 인증 서버의 public_id 는 UUID 다 */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** 토큰을 검증하는 데 필요한 설정. */
export type TokenSettings = Pick<Environment, 'JWT_ISSUER' | 'JWT_AUDIENCE'>;

/**
 * 토큰을 받아들일 수 없다.
 *
 * 이유를 나누지 않는다. 만료인지 서명이 틀렸는지를 알려 주면 토큰을 꾸며 내는 쪽에 도움이 된다.
 */
export class InvalidTokenError extends Error {}

/** 검증을 마친 토큰에서 꺼낸 값. 이 값이 있다는 것이 검증을 통과했다는 뜻이다. */
export interface AccessClaims {
  /** 인증 서버의 public_id. 게시판 서버는 사용자를 이 값으로만 가리킨다 */
  readonly userId: string;
  /** 토큰이 만료되는 시각(exp) */
  readonly expiresAt: Date;
  /** 세션 버전(ver). 인증 서버가 사용자의 세션을 모두 끊으면 오른다. 끊긴 세션 목록과 맞춰 본다 */
  readonly version: number;
  /**
   * 인증 서버가 실어 보낸 닉네임(nickname). 없거나 받아들일 수 없는 값이면 undefined 다(authors/nickname.ts).
   * 없어도 토큰은 받는다. 이 클레임이 생기기 전에 발급한 토큰이 있다
   */
  readonly nickname?: string;
}

/**
 * 서명을 확인하기 전에 머리말만 읽어, 어느 키로 확인할지(kid) 알아낸다.
 *
 * 이 시점의 값은 아직 믿을 수 없다. 키를 고르는 데만 쓴다.
 */
export function readKeyId(token: string): string {
  let header: { alg?: unknown; kid?: unknown };
  try {
    header = decodeProtectedHeader(token);
  } catch (error) {
    throw new InvalidTokenError(undefined, { cause: error });
  }

  const keyId = header.kid;
  if (header.alg !== ALGORITHM || typeof keyId !== 'string' || keyId === '') {
    throw new InvalidTokenError();
  }
  return keyId;
}

/** 서명, 만료, 발급자, 대상을 확인하고 토큰 안의 값을 돌려준다. 하나라도 틀리면 InvalidTokenError 다. */
export async function decodeClaims(
  token: string,
  key: CryptoKey,
  settings: TokenSettings,
): Promise<JWTPayload> {
  try {
    const { payload } = await jwtVerify(token, key, {
      algorithms: [ALGORITHM],
      issuer: settings.JWT_ISSUER,
      audience: settings.JWT_AUDIENCE,
      clockTolerance: CLOCK_SKEW_SECONDS,
      requiredClaims: REQUIRED_CLAIMS,
    });
    return payload;
  } catch (error) {
    if (error instanceof errors.JOSEError) {
      throw new InvalidTokenError(undefined, { cause: error });
    }
    throw error;
  }
}

/** 세션 버전(ver)을 읽는다. 없으면 0 이다. 0 이상의 정수가 아니면 받아들일 수 없는 토큰이다. */
export function readSessionVersion(value: unknown): number {
  if (value === undefined) {
    return DEFAULT_SESSION_VERSION;
  }
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    throw new InvalidTokenError();
  }
  return value as number;
}

/**
 * 토큰 안의 값에서 이 서버가 쓰는 것만 꺼낸다. access 토큰이 아니거나 주인의 ID 가 UUID 가 아니면 거부한다.
 * 닉네임은 받아들일 수 있을 때만 싣는다. 이상한 닉네임 때문에 토큰을 거부하지 않는다.
 */
export function buildAccessClaims(claims: JWTPayload): AccessClaims {
  if (claims.token_type !== ACCESS_TOKEN_TYPE) {
    throw new InvalidTokenError();
  }
  if (typeof claims.sub !== 'string' || !UUID.test(claims.sub)) {
    throw new InvalidTokenError();
  }
  if (typeof claims.exp !== 'number') {
    throw new InvalidTokenError();
  }
  const nickname = readNickname(claims.nickname);
  return {
    userId: claims.sub.toLowerCase(),
    expiresAt: new Date(claims.exp * 1000),
    version: readSessionVersion(claims.ver),
    ...(nickname === undefined ? {} : { nickname }),
  };
}

/**
 * access 토큰을 검증하고 그 안의 값을 돌려준다.
 *
 * 토큰이 틀렸으면 InvalidTokenError 다.
 * 키를 구할 수 없어 맞는지 틀린지 알 수 없으면 JwksUnavailableError 가 그대로 올라간다.
 */
export async function verifyAccessToken(
  token: string,
  jwks: JwksCache,
  settings: TokenSettings,
): Promise<AccessClaims> {
  const keyId = readKeyId(token);
  let key: CryptoKey;
  try {
    key = await jwks.getKey(keyId);
  } catch (error) {
    if (error instanceof UnknownKeyError) {
      throw new InvalidTokenError(undefined, { cause: error });
    }
    throw error;
  }

  return buildAccessClaims(await decodeClaims(token, key, settings));
}
