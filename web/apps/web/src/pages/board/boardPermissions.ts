// web/apps/web/src/pages/board/boardPermissions.ts
// 누구에게 어떤 단추를 보일지. 순수한 함수다. 규칙은 게시판 서버(board-server/app/posts/policy.py, comments/policy.py)와 같다.
// 화면의 숨김은 편의다. 서버가 다시 막는다(403). 나를 아직 모르면(읽는 중) 고치기·지우기·신고를 보이지 않는다.

import type { Board, BoardComment, BoardMe } from '../../api/types';

type Authored = { author_id: string | null };

function isOperatorBoard(board: Pick<Board, 'write_policy'> | undefined): boolean {
  return board?.write_policy === 'operator';
}

function isMine(item: Authored, me: BoardMe | undefined): boolean {
  return me !== undefined && item.author_id !== null && item.author_id === me.user_id;
}

/** 글쓰기 단추. 누구나 쓰는 게시판이면 로그인 전에도 보인다(누르면 로그인으로). 운영자 게시판은 운영자에게만 */
export function canWritePost(board: Pick<Board, 'write_policy'> | undefined, me: BoardMe | undefined): boolean {
  if (!board) return false;
  return !isOperatorBoard(board) || me?.is_operator === true;
}

/** 글 고치기. 글쓴이만. 운영자 게시판의 글은 지금도 운영자인 글쓴이만 */
export function canEditPost(post: Authored, board: Pick<Board, 'write_policy'> | undefined, me: BoardMe | undefined): boolean {
  if (!isMine(post, me)) return false;
  return !isOperatorBoard(board) || me?.is_operator === true;
}

/** 글 지우기. 글쓴이와 운영자. 운영자 게시판의 글은 운영자만 */
export function canDeletePost(post: Authored, board: Pick<Board, 'write_policy'> | undefined, me: BoardMe | undefined): boolean {
  if (me === undefined) return false;
  if (isOperatorBoard(board)) return me.is_operator;
  return isMine(post, me) || me.is_operator;
}

/** 고정과 풀기. 운영자만 */
export function canPin(me: BoardMe | undefined): boolean {
  return me?.is_operator === true;
}

/** 댓글 고치기. 글쓴이만. 지운 자리는 고치지 못한다 */
export function canEditComment(comment: Pick<BoardComment, 'author_id' | 'deleted'>, me: BoardMe | undefined): boolean {
  return !comment.deleted && isMine(comment, me);
}

/** 댓글 지우기. 글쓴이와 운영자 */
export function canDeleteComment(comment: Pick<BoardComment, 'author_id' | 'deleted'>, me: BoardMe | undefined): boolean {
  if (comment.deleted || me === undefined) return false;
  return isMine(comment, me) || me.is_operator;
}

/** 신고. 로그인한 사람이 남의 것을. 지운 것은 신고하지 못한다 */
export function canReport(item: Authored & { deleted?: boolean }, me: BoardMe | undefined): boolean {
  return me !== undefined && item.deleted !== true && !isMine(item, me);
}

/** 답글 달기. 지우지 않은 댓글에(답글에는 달지 못한다) */
export function canReply(comment: Pick<BoardComment, 'parent_id' | 'deleted'>): boolean {
  return comment.parent_id === null && !comment.deleted;
}
