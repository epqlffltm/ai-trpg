// board-server/src/notifications/notices.ts

/**
 * 게시판의 일에서 누구에게 무슨 알림을 보낼지 정한다(#385). DB 도 Nest 도 모르는 순수한 함수들이다.
 *
 *   - post.commented: 내 글에 댓글이 달렸다. 글쓴이에게 간다
 *   - comment.replied: 내 댓글에 답글이 달렸다. 그 댓글의 글쓴이에게 간다
 *
 * 자기 글에 자기가 단 댓글, 자기 댓글에 자기가 단 답글은 알리지 않는다.
 * 답글은 댓글의 글쓴이에게만 간다. 글쓴이에게 "글에 댓글이 달렸다"를 또 보내지 않는다. 답글마다 둘씩 가면 시끄럽다.
 *
 * 열쇠(source_key)는 "<kind>:<댓글 번호>" 다. 댓글 하나에 알림은 하나라서 다시 보내도 같은 열쇠다.
 * 내용에는 어디서 일어났는지(게시판, 글, 댓글의 번호와 글의 제목)만 싣는다. 댓글의 글은 싣지 않는다.
 * 댓글을 지워도 알림함에는 남기 때문이다. 화면은 글로 가서 댓글을 본다.
 */

export const POST_COMMENTED = 'post.commented';
export const COMMENT_REPLIED = 'comment.replied';

/** 발송함에 적을 알림 하나. */
export interface NewNotice {
  userId: string;
  kind: string;
  sourceKey: string;
  payload: Record<string, unknown>;
}

/** 새 댓글이 달린 곳. 알림을 정하는 데 필요한 것만 담는다. */
export interface CommentContext {
  post: { id: string; title: string; authorId: string; boardSlug: string };
  /** 답글이면 단 댓글. 글에 단 댓글이면 null 이다 */
  parent: { id: string; authorId: string } | null;
  comment: { id: string; authorId: string };
}

/** 그 댓글에서 온 알림의 열쇠. */
export function commentKey(kind: string, commentId: string): string {
  return `${kind}:${commentId}`;
}

/** 알림의 내용. 어디서 일어났는지만 싣는다. */
export function commentPayload(
  context: CommentContext,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    board_slug: context.post.boardSlug,
    post_id: context.post.id,
    post_title: context.post.title,
    comment_id: context.comment.id,
  };
  if (context.parent !== null) {
    payload.parent_id = context.parent.id;
  }
  return payload;
}

/** 이 댓글을 누구에게 알리는가. 받는 사람과 종류다. 알릴 사람이 없으면 null 이다. */
export function recipientOf(
  context: CommentContext,
): { userId: string; kind: string } | null {
  const target =
    context.parent === null
      ? { userId: context.post.authorId, kind: POST_COMMENTED }
      : { userId: context.parent.authorId, kind: COMMENT_REPLIED };
  return target.userId === context.comment.authorId ? null : target;
}

/** 새 댓글 하나에서 나오는 알림들. 없거나 하나다. */
export function noticesForComment(context: CommentContext): NewNotice[] {
  const recipient = recipientOf(context);
  if (recipient === null) {
    return [];
  }
  return [
    {
      ...recipient,
      sourceKey: commentKey(recipient.kind, context.comment.id),
      payload: commentPayload(context),
    },
  ];
}
