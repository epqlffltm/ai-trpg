// board-server/src/comment-counts/counts.spec.ts

/**
 * 글마다의 댓글 수를 다루는 셈(counts.ts)을 검증한다.
 */

import { countOf, countsFrom } from './counts.js';

describe('countsFrom', () => {
  it('DB 가 글자로 준 수를 숫자로 바꿔 글 번호로 찾게 한다', () => {
    const counts = countsFrom([
      { postId: '1', count: '3' },
      { postId: '9007199254740993', count: '12' },
    ]);

    expect(countOf(counts, '1')).toBe(3);
    // 글 번호는 글자 그대로 견준다. 숫자로 바꾸면 큰 번호가 뭉개진다
    expect(countOf(counts, '9007199254740993')).toBe(12);
    expect(countOf(counts, '9007199254740992')).toBe(0);
  });

  it('줄이 없으면 빈 표다', () => {
    expect(countsFrom([]).size).toBe(0);
  });
});

describe('countOf', () => {
  it('표에 없는 글은 댓글이 0개다', () => {
    // 댓글이 없는 글은 DB 가 줄을 돌려주지 않는다
    expect(countOf(countsFrom([{ postId: '1', count: '3' }]), '2')).toBe(0);
  });
});
