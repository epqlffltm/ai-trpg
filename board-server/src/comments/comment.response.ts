// board-server/src/comments/comment.response.ts

/**
 * 댓글을 응답의 모양으로 바꾼다. 순수한 함수들이다.
 *
 * 칸 이름은 밑줄로 잇고, 번호는 글자로 내보낸다. 글과 같다.
 * 지운 댓글은 답글이 달려 있을 때만 목록에 나온다. 그때는 자리만 보여 준다.
 * 누가 무엇을 썼는지(author_id, content)는 비우고 deleted 를 true 로 둔다.
 */

import { Comment } from './comment.entity.js';

/** 댓글 하나. */
export interface CommentResponse {
  id: string;
  post_id: string;
  /** 답글이면 어느 댓글에 단 것인가. 글에 단 댓글이면 null */
  parent_id: string | null;
  /** 글쓴이. 지운 댓글이면 null */
  author_id: string | null;
  /** 내용. 지운 댓글이면 null */
  content: string | null;
  /** 지운 댓글인가. 답글이 달려 있어 자리만 남은 것이다 */
  deleted: boolean;
  created_at: string;
  updated_at: string;
}

/** 목록의 한 줄. 글에 단 댓글 하나와 거기 달린 답글들이다. */
export interface CommentThreadResponse extends CommentResponse {
  replies: CommentResponse[];
}

/** 글에 단 댓글 하나와 거기 달린 답글들. */
export interface CommentThread {
  comment: Comment;
  replies: Comment[];
}

/** 응답에 싣는 데 필요한 댓글의 칸들. */
export type CommentFields = Pick<
  Comment,
  | 'id'
  | 'postId'
  | 'parentId'
  | 'authorId'
  | 'content'
  | 'createdAt'
  | 'updatedAt'
  | 'deletedAt'
>;

export function toCommentResponse(comment: CommentFields): CommentResponse {
  const deleted = comment.deletedAt !== null;
  return {
    id: comment.id,
    post_id: comment.postId,
    parent_id: comment.parentId,
    author_id: deleted ? null : comment.authorId,
    content: deleted ? null : comment.content,
    deleted,
    created_at: comment.createdAt.toISOString(),
    updated_at: comment.updatedAt.toISOString(),
  };
}

export function toCommentThreadResponse(
  thread: CommentThread,
): CommentThreadResponse {
  return {
    ...toCommentResponse(thread.comment),
    replies: thread.replies.map(toCommentResponse),
  };
}
