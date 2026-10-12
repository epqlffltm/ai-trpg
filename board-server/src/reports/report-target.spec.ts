// board-server/src/reports/report-target.spec.ts

/**
 * 신고하는 것을 가리키는 값(report-target.ts)을 검증한다.
 */

import {
  commentTarget,
  postTarget,
  targetColumns,
  targetOf,
  whereTarget,
} from './report-target.js';

describe('targetColumns', () => {
  it('글이면 post_id 만 찬다', () => {
    expect(targetColumns(postTarget('7'))).toEqual({
      postId: '7',
      commentId: null,
    });
  });

  it('댓글이면 comment_id 만 찬다', () => {
    expect(targetColumns(commentTarget('7'))).toEqual({
      postId: null,
      commentId: '7',
    });
  });
});

describe('whereTarget', () => {
  it('비어 있는 칸은 조건에 넣지 않는다', () => {
    expect(whereTarget(postTarget('7'))).toEqual({ postId: '7' });
    expect(whereTarget(commentTarget('7'))).toEqual({ commentId: '7' });
  });
});

describe('targetOf', () => {
  it('찬 칸으로 무엇인지 읽는다', () => {
    expect(targetOf({ postId: '3', commentId: null })).toEqual(postTarget('3'));
    expect(targetOf({ postId: null, commentId: '4' })).toEqual(
      commentTarget('4'),
    );
  });

  it('targetColumns 와 짝이 맞는다', () => {
    for (const target of [postTarget('1'), commentTarget('2')]) {
      expect(targetOf(targetColumns(target))).toEqual(target);
    }
  });

  it('둘 다 비어 있으면 예외다. DB 가 막는 행이다', () => {
    expect(() => targetOf({ postId: null, commentId: null })).toThrow();
  });
});
