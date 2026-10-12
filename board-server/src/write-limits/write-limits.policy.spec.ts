// board-server/src/write-limits/write-limits.policy.spec.ts

/**
 * 쓰기 횟수 제한의 값과 셈(write-limits.policy.ts)을 검증한다.
 */

import { retryAfterSeconds, WRITE_LIMITS } from './write-limits.policy.js';

describe('한도', () => {
  it('글은 10분에 5개, 댓글은 1분에 10개, 신고는 1시간에 20건이다', () => {
    expect(WRITE_LIMITS).toEqual({
      post: { windowSeconds: 600, max: 5 },
      comment: { windowSeconds: 60, max: 10 },
      report: { windowSeconds: 3600, max: 20 },
    });
  });
});

describe('retryAfterSeconds', () => {
  it('올림한 정수다', () => {
    expect(retryAfterSeconds(141.2)).toBe(142);
    expect(retryAfterSeconds(142)).toBe(142);
  });

  it('DB 가 글자로 준 숫자도 읽는다', () => {
    expect(retryAfterSeconds('141.2')).toBe(142);
  });

  it.each([0, -3, 0.0001, Number.NaN, 'abc', null, undefined])(
    '1 보다 작거나 숫자가 아니면(%j) 1 이다',
    (remaining) => {
      // 0.0001 은 올림하면 1 이다. 나머지는 "0초 뒤에 다시"가 되지 않게 1 로 올린다
      expect(retryAfterSeconds(remaining)).toBe(1);
    },
  );
});
