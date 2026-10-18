// board-server/src/notifications/notices.spec.ts

/**
 * 누구에게 무슨 알림을 보낼지(notices.ts)를 검증한다. DB 를 쓰지 않는다.
 */

import {
  COMMENT_REPLIED,
  CommentContext,
  noticesForComment,
  POST_COMMENTED,
} from './notices.js';

const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const COMMENTER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const REPLIER = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';

/** 글쓴이(WRITER)의 글에 commenter 가 단 댓글(7번). parent 를 주면 답글이다. */
function context(
  commenter: string,
  parent: CommentContext['parent'] = null,
): CommentContext {
  return {
    post: { id: '3', title: '첫 모험', authorId: WRITER, boardSlug: 'free' },
    parent,
    comment: { id: '7', authorId: commenter },
  };
}

describe('noticesForComment', () => {
  it('남의 글에 단 댓글은 글쓴이에게 알린다', () => {
    expect(noticesForComment(context(COMMENTER))).toEqual([
      {
        userId: WRITER,
        kind: POST_COMMENTED,
        sourceKey: 'post.commented:7',
        payload: {
          board_slug: 'free',
          post_id: '3',
          post_title: '첫 모험',
          comment_id: '7',
        },
      },
    ]);
  });

  it('자기 글에 단 댓글은 알리지 않는다', () => {
    expect(noticesForComment(context(WRITER))).toEqual([]);
  });

  it('답글은 그 댓글의 글쓴이에게만 알린다. 글쓴이에게 또 보내지 않는다', () => {
    const notices = noticesForComment(
      context(REPLIER, { id: '5', authorId: COMMENTER }),
    );

    expect(notices).toEqual([
      {
        userId: COMMENTER,
        kind: COMMENT_REPLIED,
        sourceKey: 'comment.replied:7',
        payload: {
          board_slug: 'free',
          post_id: '3',
          post_title: '첫 모험',
          comment_id: '7',
          parent_id: '5',
        },
      },
    ]);
  });

  it('자기 댓글에 단 답글은 알리지 않는다. 글쓴이가 답해도 같다', () => {
    expect(
      noticesForComment(context(COMMENTER, { id: '5', authorId: COMMENTER })),
    ).toEqual([]);
    expect(
      noticesForComment(context(WRITER, { id: '5', authorId: WRITER })),
    ).toEqual([]);
  });

  it('글쓴이가 남의 댓글에 답하면 그 댓글의 글쓴이에게 간다', () => {
    const [notice] = noticesForComment(
      context(WRITER, { id: '5', authorId: COMMENTER }),
    );

    expect([notice.userId, notice.kind]).toEqual([COMMENTER, COMMENT_REPLIED]);
  });
});
