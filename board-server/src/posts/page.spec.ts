// board-server/src/posts/page.spec.ts

/**
 * 목록을 쪽으로 나누는 셈(page.ts)을 검증한다.
 */

import { offsetOf, pageOf } from './page.js';

describe('offsetOf', () => {
  it.each([
    [1, 20, 0],
    [2, 20, 20],
    [3, 50, 100],
    [10000, 50, 499950],
  ])('%i쪽, 한 쪽에 %i개면 %i개를 건너뛴다', (page, size, offset) => {
    expect(offsetOf(page, size)).toBe(offset);
  });
});

describe('pageOf', () => {
  it('항목들과 쪽, 크기, 전체 개수를 묶는다', () => {
    expect(pageOf(['a', 'b'], 2, 20, 22)).toEqual({
      items: ['a', 'b'],
      page: 2,
      size: 20,
      total: 22,
    });
  });
});
