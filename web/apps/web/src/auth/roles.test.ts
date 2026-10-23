// web/apps/web/src/auth/roles.test.ts
// access 토큰에서 역할을 읽는다. 서명은 보지 않는다. 모양이 틀린 토큰은 역할이 없는 것이다.

import { describe, expect, it } from 'vitest';
import { decodeBase64Url, isOperator, rolesOf, tokenClaims } from './roles';

function base64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function token(claims: unknown): string {
  return `${base64Url('{"alg":"RS256"}')}.${base64Url(JSON.stringify(claims))}.signature`;
}

function session(accessToken: string) {
  return { accessToken, consentsPending: [], withdrawalScheduledAt: null };
}

describe('역할', () => {
  it('토큰의 roles 를 읽는다', () => {
    expect(rolesOf(token({ sub: 'u1', roles: ['operator', 7] }))).toEqual(['operator']);
    expect(rolesOf(token({ sub: 'u1' }))).toEqual([]);
    expect(rolesOf(token({ roles: 'operator' }))).toEqual([]);
  });

  it('base64url 의 - 와 _, 빠진 = 와 한글을 푼다', () => {
    const text = '{"nick":"모험가??>>"}';
    expect(base64Url(text)).toMatch(/[-_]/);
    expect(decodeBase64Url(base64Url(text))).toBe(text);
    expect(tokenClaims(token({ nick: '모험가' }))).toEqual({ nick: '모험가' });
  });

  it('모양이 틀린 토큰은 역할이 없다', () => {
    expect(rolesOf('a1')).toEqual([]);
    expect(rolesOf('a.!!!.c')).toEqual([]);
    expect(rolesOf(`a.${base64Url('[1]')}.c`)).toEqual([]);
    expect(rolesOf(`a.${base64Url('null')}.c`)).toEqual([]);
  });

  it('운영자인지는 로그인과 역할로 정한다', () => {
    expect(isOperator(null)).toBe(false);
    expect(isOperator(session(token({ roles: [] })))).toBe(false);
    expect(isOperator(session(token({ roles: ['operator'] })))).toBe(true);
  });
});
