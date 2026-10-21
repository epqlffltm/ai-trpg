// board-server/src/comments/comments.policy.ts

/**
 * 댓글에 관한 규칙. DB 도 Nest 도 모르는 순수한 함수들이다.
 *
 *   - 쓰기: 로그인한 누구나. 운영자만 글을 쓰는 게시판(공지사항)의 글에도 댓글은 누구나 단다.
 *   - 답글: 글에 단 댓글에만 단다. 답글에는 달지 못한다. 한 댓글에 달 수 있는 수에 끝이 있다.
 *   - 고치기: 글쓴이만. 지우기: 글쓴이와 운영자. 글과 같다.
 */

import { Comment } from './comment.entity.js';

/**
 * 한 댓글에 달 수 있는 답글의 수.
 * 댓글 목록은 댓글마다 답글을 모두 실어 보낸다. 끝이 없으면 한 댓글에 답글을 쏟아부어 응답을 한없이 키울 수 있다
 */
export const MAX_REPLIES_PER_COMMENT = 100;

/** 이 댓글은 답글인가. */
export function isReply(comment: Pick<Comment, 'parentId'>): boolean {
  return comment.parentId !== null;
}

/** 이 댓글에 답글을 달 수 있는 종류인가. 글에 단 댓글에만 단다. */
export function canHaveReplies(comment: Pick<Comment, 'parentId'>): boolean {
  return !isReply(comment);
}

/** 답글이 지금 replyCount 개 달린 댓글에 하나 더 달 자리가 있는가. */
export function hasRoomForReply(replyCount: number): boolean {
  return replyCount < MAX_REPLIES_PER_COMMENT;
}

/** 이 사람이 이 댓글의 글쓴이인가. 글쓴이가 탈퇴한 댓글(null)은 누구의 것도 아니다. 고칠 수 없고 운영자만 지운다. */
export function isAuthor(
  comment: Pick<Comment, 'authorId'>,
  userId: string,
): boolean {
  return comment.authorId === userId;
}

/** 이 댓글을 고쳐도 되는가. 글쓴이만이다. */
export function canEdit(
  comment: Pick<Comment, 'authorId'>,
  userId: string,
): boolean {
  return isAuthor(comment, userId);
}

/** 이 댓글을 지워도 되는가. 글쓴이와 운영자다. */
export function canDelete(
  comment: Pick<Comment, 'authorId'>,
  userId: string,
  isOperator: boolean,
): boolean {
  return isAuthor(comment, userId) || isOperator;
}
