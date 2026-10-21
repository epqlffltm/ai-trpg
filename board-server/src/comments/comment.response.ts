// board-server/src/comments/comment.response.ts

/**
 * 댓글을 응답의 모양으로 바꾼다. 순수한 함수들이다.
 *
 * 칸 이름은 밑줄로 잇고, 번호는 글자로 내보낸다. 글과 같다.
 * 지운 댓글은 답글이 달려 있을 때만 목록에 나온다. 그때는 자리만 보여 준다.
 * 누가 무엇을 썼는지(author_id, author_nickname, content)는 비우고 deleted 를 true 로 둔다.
 * 글쓴이의 닉네임은 댓글의 칸이 아니다. 따로 읽은 표(authors/)에서 찾는다.
 * 글쓴이가 탈퇴했으면 ID 와 닉네임이 null 이고 author_withdrawn 이 true 다. 지운 댓글은 누가 썼는지 보이지 않으므로 false 다.
 *
 * 응답의 모양은 인터페이스가 아니라 클래스로 적는다. API 목록(docs/api/board.openapi.json)이 빌드할 때 클래스의 칸과 주석을 읽는다.
 */

import { nicknameOf, Nicknames } from '../authors/nicknames.js';
import { Comment } from './comment.entity.js';
import { Slice } from './slice.js';

/** 댓글 하나. */
export class CommentResponse {
  id: string;
  post_id: string;
  /** 답글이면 어느 댓글에 단 것인가. 글에 단 댓글이면 null */
  parent_id: string | null;
  /** 글쓴이. 지운 댓글이거나 탈퇴한 사람이면 null */
  author_id: string | null;
  /** 글쓴이의 닉네임. 지운 댓글이거나, 이 서버가 이름을 모르는 사람이거나, 탈퇴한 사람이면 null */
  author_nickname: string | null;
  /** 글쓴이가 탈퇴했는가. 지운 댓글이면 false 다 */
  author_withdrawn: boolean;
  /** 내용. 지운 댓글이면 null */
  content: string | null;
  /** 지운 댓글인가. 답글이 달려 있어 자리만 남은 것이다 */
  deleted: boolean;
  created_at: string;
  updated_at: string;
}

/** 목록의 한 줄. 글에 단 댓글 하나와 거기 달린 답글들이다. */
export class CommentThreadResponse extends CommentResponse {
  replies: CommentResponse[];
}

/** 댓글 목록의 한 토막. 셈과 모양은 slice.ts 의 Slice<Item> 이 정한다. 목록 도구가 제네릭을 읽지 못해 클래스로 적는다. */
export class CommentListResponse implements Slice<CommentThreadResponse> {
  items: CommentThreadResponse[];
  /** 다음 토막을 부를 때 after 에 넣을 값. 뒤에 더 없으면 null 이다 */
  next: string | null;
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

export function toCommentResponse(
  comment: CommentFields,
  nicknames: Nicknames,
): CommentResponse {
  const deleted = comment.deletedAt !== null;
  return {
    id: comment.id,
    post_id: comment.postId,
    parent_id: comment.parentId,
    author_id: deleted ? null : comment.authorId,
    author_nickname: deleted ? null : nicknameOf(nicknames, comment.authorId),
    author_withdrawn: !deleted && comment.authorId === null,
    content: deleted ? null : comment.content,
    deleted,
    created_at: comment.createdAt.toISOString(),
    updated_at: comment.updatedAt.toISOString(),
  };
}

export function toCommentThreadResponse(
  thread: CommentThread,
  nicknames: Nicknames,
): CommentThreadResponse {
  return {
    ...toCommentResponse(thread.comment, nicknames),
    replies: thread.replies.map((reply) => toCommentResponse(reply, nicknames)),
  };
}

/** 댓글들(답글 포함)을 쓴 사람들의 번호. 지운 댓글은 뺀다. 이름을 읽을 사람들이다. 탈퇴한 사람은 null 이다. */
export function authorsOf(
  threads: readonly CommentThread[],
): (string | null)[] {
  return threads
    .flatMap((thread) => [thread.comment, ...thread.replies])
    .filter((comment) => comment.deletedAt === null)
    .map((comment) => comment.authorId);
}
