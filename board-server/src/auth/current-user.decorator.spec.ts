// board-server/src/auth/current-user.decorator.spec.ts

/**
 * 요청에서 토큰의 주인을 꺼내는 함수(current-user.decorator.ts 의 userOf)를 검증한다.
 * 컨트롤러의 인자로 들어오는지는 test/auth.e2e-spec.ts 가 본다.
 */

import { userOf } from './current-user.decorator.js';
import { AccessClaims } from './tokens.js';

const USER: AccessClaims = {
  userId: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
  expiresAt: new Date('2027-01-15T08:00:00.000Z'),
  version: 1,
  isOperator: false,
};

describe('userOf', () => {
  it('문지기가 적어 둔 토큰의 주인을 꺼낸다', () => {
    expect(userOf({ user: USER })).toBe(USER);
  });

  it('주인이 적혀 있지 않으면 예외를 낸다', () => {
    // 로그인 없이 부르는 API 에서 주인을 꺼내려 한 것이다. 조용히 넘기지 않는다
    expect(() => userOf({})).toThrow('로그인 없이');
  });
});
