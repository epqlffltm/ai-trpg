// board-server/src/auth/roles.spec.ts

/**
 * 토큰의 역할을 읽는 규칙을 검증한다. 게임 서버(tests/test_tokens.py)와 같은 경우를 본다.
 */

import { OPERATOR_ROLE, readIsOperator } from './roles.js';

describe('readIsOperator', () => {
  it('목록에 operator 가 있으면 운영자다', () => {
    expect(readIsOperator([OPERATOR_ROLE])).toBe(true);
  });

  it('모르는 역할이 함께 있어도 operator 가 있으면 운영자다', () => {
    expect(readIsOperator(['tester', OPERATOR_ROLE])).toBe(true);
  });

  it('빈 목록이나 모르는 역할뿐이면 운영자가 아니다', () => {
    expect(readIsOperator([])).toBe(false);
    expect(readIsOperator(['admin'])).toBe(false);
  });

  it('칸이 없으면 운영자가 아니다', () => {
    expect(readIsOperator(undefined)).toBe(false);
  });

  it('목록이 아니면 운영자가 아니다', () => {
    expect(readIsOperator(OPERATOR_ROLE)).toBe(false);
    expect(readIsOperator({ operator: true })).toBe(false);
    expect(readIsOperator(null)).toBe(false);
  });

  it('대소문자가 다르면 운영자가 아니다', () => {
    expect(readIsOperator(['Operator'])).toBe(false);
  });
});
