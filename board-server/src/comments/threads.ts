// board-server/src/comments/threads.ts

/**
 * 댓글들과 답글들을 "댓글 하나와 거기 달린 답글들"로 묶는다. 순수한 함수다.
 */

import { Comment } from './comment.entity.js';
import { CommentThread } from './comment.response.js';

/**
 * 댓글마다 제 답글을 붙인다. 댓글의 차례와 답글의 차례는 받은 그대로 둔다.
 *
 * 어느 댓글의 것도 아닌 답글은 버린다. 답글이 없는 댓글은 빈 목록을 갖는다.
 */
export function threadsOf(
  comments: Comment[],
  replies: Comment[],
): CommentThread[] {
  const repliesByParent = new Map<string, Comment[]>(
    comments.map((comment) => [comment.id, []]),
  );
  for (const reply of replies) {
    repliesByParent.get(reply.parentId ?? '')?.push(reply);
  }
  return comments.map((comment) => ({
    comment,
    replies: repliesByParent.get(comment.id) ?? [],
  }));
}
