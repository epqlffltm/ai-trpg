// board-server/src/auth/bearer.spec.ts

/**
 * Authorization 머리말에서 토큰을 꺼내는 함수(bearer.ts)를 검증한다.
 */

import { readBearerToken } from './bearer.js';

describe('readBearerToken', () => {
  it('Bearer 뒤의 토큰을 꺼낸다', () => {
    expect(readBearerToken('Bearer abc.def.ghi')).toBe('abc.def.ghi');
  });

  it.each(['bearer abc', 'BEARER abc', 'BeArEr abc'])(
    '방식의 이름은 대소문자를 가리지 않는다(%j)',
    (header) => {
      expect(readBearerToken(header)).toBe('abc');
    },
  );

  it('앞뒤와 사이의 빈칸을 봐준다', () => {
    expect(readBearerToken('  Bearer   abc  ')).toBe('abc');
  });

  it.each([undefined, null, 42, ['Bearer abc']])(
    '머리말이 글자가 아니면(%j) 없는 것으로 본다',
    (header) => {
      expect(readBearerToken(header)).toBeUndefined();
    },
  );

  it.each([
    '',
    'Bearer',
    'Bearer ',
    'abc',
    'Basic dXNlcjpwYXNz',
    'Token abc',
    'Bearerabc',
    'Bearer abc def',
  ])('Bearer 토큰의 모양이 아니면(%j) 없는 것으로 본다', (header) => {
    expect(readBearerToken(header)).toBeUndefined();
  });
});
