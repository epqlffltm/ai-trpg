// board-server/src/comments/comment-id.pipe.spec.ts

/**
 * 주소의 댓글 번호를 검사하는 파이프(comment-id.pipe.ts)를 검증한다.
 * 번호의 모양 자체는 src/ids/record-id.spec.ts 가 본다.
 */

import { NotFoundException } from '@nestjs/common';
import { CommentIdPipe } from './comment-id.pipe.js';

describe('CommentIdPipe', () => {
  it('댓글 번호를 글자 그대로 돌려준다', () => {
    expect(new CommentIdPipe().transform('57')).toBe('57');
  });

  it.each(['abc', '0', '-1', undefined])(
    '댓글 번호의 모양이 아니면(%j) 그런 댓글이 없는 것이다',
    (value) => {
      expect(() => new CommentIdPipe().transform(value)).toThrow(
        NotFoundException,
      );
    },
  );
});
