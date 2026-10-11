// board-server/src/auth/bearer.ts

/**
 * 요청의 Authorization 머리말에서 토큰을 꺼낸다. Nest 를 모르는 순수한 함수다.
 */

/** "Bearer <토큰>" 의 모양. 방식의 이름은 대소문자를 가리지 않는다(RFC 9110) */
const BEARER = /^Bearer +(\S+)$/i;

/**
 * Authorization 머리말에서 Bearer 토큰을 꺼낸다. 머리말이 없거나 다른 방식이면 undefined 다.
 *
 * 토큰이 맞는지는 보지 않는다. 꺼내기만 한다.
 */
export function readBearerToken(header: unknown): string | undefined {
  if (typeof header !== 'string') {
    return undefined;
  }
  return BEARER.exec(header.trim())?.[1];
}
