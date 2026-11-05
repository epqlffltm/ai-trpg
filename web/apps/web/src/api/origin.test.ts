// web/apps/web/src/api/origin.test.ts
// API 의 출처(VITE_API_ORIGIN)를 읽는 규칙과 주소를 만드는 것을 본다.

import { describe, expect, it } from 'vitest';

import { apiOrigin, apiUrl } from './origin';

describe('apiOrigin', () => {
  it('비었으면 같은 출처(빈 글자)다', () => {
    expect(apiOrigin(undefined)).toBe('');
    expect(apiOrigin('')).toBe('');
    expect(apiOrigin('  ')).toBe('');
  });

  it('출처는 그대로 쓰고 끝의 / 는 뗀다', () => {
    expect(apiOrigin('https://play.example.com')).toBe('https://play.example.com');
    expect(apiOrigin('https://play.example.com/')).toBe('https://play.example.com');
    expect(apiOrigin('http://localhost:8080')).toBe('http://localhost:8080');
  });

  it('경로나 물음표가 붙거나 출처가 아니면 멈춘다', () => {
    expect(() => apiOrigin('https://play.example.com/api')).toThrow('VITE_API_ORIGIN');
    expect(() => apiOrigin('https://play.example.com?x=1')).toThrow('VITE_API_ORIGIN');
    expect(() => apiOrigin('play.example.com')).toThrow('VITE_API_ORIGIN');
    expect(() => apiOrigin('javascript:alert(1)')).toThrow('VITE_API_ORIGIN');
  });
});

describe('apiUrl', () => {
  it('출처가 없으면 경로 그대로다(웹)', () => {
    expect(apiUrl('/api/v1/auth/me', '')).toBe('/api/v1/auth/me');
  });

  it('출처가 있으면 앞에 붙인다(앱)', () => {
    expect(apiUrl('/api/v1/auth/me', 'https://play.example.com')).toBe('https://play.example.com/api/v1/auth/me');
  });

  it('시험의 기본값은 같은 출처다', () => {
    expect(apiUrl('/api/v1/game/me')).toBe('/api/v1/game/me');
  });
});
