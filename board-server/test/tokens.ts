// board-server/test/tokens.ts

/**
 * 테스트가 토큰을 만들 때 함께 쓰는 도구. 인증 서버 없이, 테스트가 직접 만든 키로 서명한다.
 *
 * 인증 서버가 발급하는 access 토큰과 같은 모양으로 만든다(auth-server/accounts/tokens.py).
 * 머리말에 kid, 안에는 iss, aud(목록), sub(public_id), exp, token_type 이 있다.
 * 테스트는 여기서 한 가지씩만 틀리게 바꿔, 그 하나 때문에 거부되는지 본다.
 */

import { exportJWK, generateKeyPair, JWK, SignJWT } from 'jose';
import { ALGORITHM, Keys, parseJwks } from '../src/auth/jwks.js';

/** 인증 서버의 이름(iss). 서버의 기본 설정과 같다 */
export const ISSUER = 'ai-trpg-auth';
/** 게시판 서버의 이름(aud). 서버의 기본 설정과 같다 */
export const AUDIENCE = 'ai-trpg-board';
/** 인증 서버가 토큰에 싣는 대상의 목록 */
export const AUDIENCES = ['ai-trpg-auth', 'ai-trpg-game', AUDIENCE];
/** 테스트에 쓰는 사용자의 public_id */
export const USER_ID = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';

/** 서명에 쓰는 키 한 벌. 개인키로 서명하고, 공개키(JWK)를 서버에 준다. */
export interface SigningKey {
  kid: string;
  privateKey: CryptoKey;
  /** JWKS 에 싣는 모양의 공개키 */
  jwk: JWK;
}

/** 토큰에서 바꿔 볼 수 있는 값들. 적지 않은 것은 맞는 값이다. */
export interface TokenOptions {
  issuer?: string;
  audience?: string | string[];
  subject?: string;
  tokenType?: string;
  /** 지금부터 몇 초 뒤에 만료되는가. 음수면 이미 만료됐다 */
  expiresInSeconds?: number;
  /** 머리말에 적는 kid. 적지 않으면 서명하는 키의 kid 다 */
  kid?: string;
  /** 토큰에 싣는 닉네임. 적지 않으면 싣지 않는다(이 클레임이 생기기 전의 토큰과 같다) */
  nickname?: string;
  /** 토큰에 싣는 세션 버전(ver). 적지 않으면 1 이다 */
  version?: number;
}

/** 새 RSA 키 한 벌을 만든다. */
export async function makeSigningKey(kid: string): Promise<SigningKey> {
  const { privateKey, publicKey } = await generateKeyPair(ALGORITHM);
  const jwk = {
    ...(await exportJWK(publicKey)),
    kid,
    use: 'sig',
    alg: ALGORITHM,
  };
  return { kid, privateKey, jwk };
}

/** 키들을 인증 서버가 내주는 JWKS 문서의 모양으로 묶는다. */
export function jwksDocument(...keys: SigningKey[]): { keys: JWK[] } {
  return { keys: keys.map((key) => key.jwk) };
}

/** 키들을 서버가 기억하는 모양(kid 로 찾는 공개키들)으로 바꾼다. */
export function publicKeys(...keys: SigningKey[]): Promise<Keys> {
  return parseJwks(jwksDocument(...keys));
}

/** 지금 시각(초). 토큰의 exp 를 셈하는 데 쓴다. */
function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

/** 인증 서버가 발급한 것과 같은 모양의 토큰을 만든다. options 로 한 가지씩 틀리게 바꾼다. */
export function signToken(
  key: SigningKey,
  options: TokenOptions = {},
): Promise<string> {
  return new SignJWT({
    token_type: options.tokenType ?? 'access',
    ver: options.version ?? 1,
    ...(options.nickname === undefined ? {} : { nickname: options.nickname }),
  })
    .setProtectedHeader({
      alg: ALGORITHM,
      typ: 'JWT',
      kid: options.kid ?? key.kid,
    })
    .setIssuer(options.issuer ?? ISSUER)
    .setAudience(options.audience ?? AUDIENCES)
    .setSubject(options.subject ?? USER_ID)
    .setExpirationTime(nowSeconds() + (options.expiresInSeconds ?? 900))
    .setJti('test-token')
    .sign(key.privateKey);
}

/** 글자를 토큰의 한 마디(base64url)로 바꾼다. */
function segment(value: object): string {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

/**
 * 서명 없이 손으로 짠 토큰을 만든다. 머리말과 내용을 마음대로 적는다.
 *
 * 서명이 없는 토큰(alg: none)처럼, 라이브러리가 만들어 주지 않는 틀린 토큰을 만들 때 쓴다.
 */
export function forgeToken(
  header: object,
  claims: object,
  signature = '',
): string {
  return `${segment(header)}.${segment(claims)}.${signature}`;
}

/** 맞는 토큰의 내용. forgeToken 에 넘긴다. */
export function validClaims(): Record<string, unknown> {
  return {
    token_type: 'access',
    iss: ISSUER,
    aud: AUDIENCES,
    sub: USER_ID,
    exp: nowSeconds() + 900,
  };
}
