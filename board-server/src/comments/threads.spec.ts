// board-server/src/comments/threads.spec.ts

/**
 * 댓글들과 답글들을 묶는 함수(threads.ts)를 검증한다.
 */

import { Comment } from './comment.entity.js';
import { threadsOf } from './threads.js';

/** 번호와 부모만 있는 댓글을 만든다. */
function comment(id: string, parentId: string | null = null): Comment {
  return { id, parentId } as Comment;
}

describe('threadsOf', () => {
  it('댓글마다 제 답글을 붙인다', () => {
    const first = comment('1');
    const second = comment('2');
    const replies = [comment('3', '1'), comment('4', '2'), comment('5', '1')];

    const threads = threadsOf([first, second], replies);

    expect(threads).toEqual([
      { comment: first, replies: [replies[0], replies[2]] },
      { comment: second, replies: [replies[1]] },
    ]);
  });

  it('답글이 없는 댓글은 빈 목록을 갖는다', () => {
    const only = comment('1');

    expect(threadsOf([only], [])).toEqual([{ comment: only, replies: [] }]);
  });

  it('댓글의 차례를 받은 그대로 둔다', () => {
    const threads = threadsOf([comment('2'), comment('1')], []);

    expect(threads.map((thread) => thread.comment.id)).toEqual(['2', '1']);
  });

  it('어느 댓글의 것도 아닌 답글은 버린다', () => {
    const threads = threadsOf([comment('1')], [comment('9', '8')]);

    expect(threads[0].replies).toEqual([]);
  });

  it('댓글이 없으면 비어 있다', () => {
    expect(threadsOf([], [comment('3', '1')])).toEqual([]);
  });
});
