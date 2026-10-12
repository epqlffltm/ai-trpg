// board-server/src/posts/posts.policy.ts

/**
 * 글에 관한 권한의 규칙. DB 도 Nest 도 모르는 순수한 함수들이다.
 *
 *   - 쓰기: 게시판이 정한 대로다. 공지처럼 운영자만 쓰는 게시판이 있다.
 *   - 고치기: 글쓴이만. 운영자도 남의 글을 고치지 못한다. 남의 이름으로 글을 바꿔 쓰는 일이 된다.
 *     운영자만 쓰는 게시판의 글은 글쓴이가 지금도 운영자여야 고친다. 지우기와 같은 까닭이다.
 *   - 지우기: 글쓴이와 운영자. 운영자만 쓰는 게시판의 글은 운영자만 지운다.
 *     공지를 쓴 사람이 운영자에서 내려온 뒤에도 그 공지를 지울 수 있으면 안 된다.
 *
 * 읽기는 누구나 한다. 규칙이 없다.
 */

import { Board } from '../boards/board.entity.js';
import { Post } from './post.entity.js';

/** 이 게시판은 운영자만 쓰는가. 운영자인지 DB 에 물어야 하는지를 이것으로 안다. */
export function isOperatorOnly(board: Pick<Board, 'writePolicy'>): boolean {
  return board.writePolicy === 'operator';
}

/** 이 게시판에 글을 써도 되는가. */
export function canWrite(
  board: Pick<Board, 'writePolicy'>,
  isOperator: boolean,
): boolean {
  return !isOperatorOnly(board) || isOperator;
}

/** 이 사람이 이 글의 글쓴이인가. */
export function isAuthor(
  post: Pick<Post, 'authorId'>,
  userId: string,
): boolean {
  return post.authorId === userId;
}

/**
 * 이 글을 고쳐도 되는가. 글쓴이만이다.
 * 운영자만 쓰는 게시판의 글은 글쓴이여도 지금 운영자가 아니면 고치지 못한다.
 * 공지는 운영의 말이다. 운영자에서 내려온 사람이 예전 공지의 내용을 바꾸면 안 된다.
 * 다른 운영자도 남의 공지를 고치지 못한다. 글쓴이의 이름으로 다른 사람이 쓴 문장이 나가게 된다.
 */
export function canEdit(
  post: Pick<Post, 'authorId'>,
  board: Pick<Board, 'writePolicy'>,
  userId: string,
  isOperator: boolean,
): boolean {
  if (!isAuthor(post, userId)) {
    return false;
  }
  return !isOperatorOnly(board) || isOperator;
}

/**
 * 고쳐도 되는지 알려면 운영자인지를 DB 에 물어야 하는가.
 * 운영자만 쓰는 게시판의 제 글일 때만 묻는다. 남의 글은 묻지 않아도 안 되고, 누구나 쓰는 게시판의 제 글은 묻지 않아도 된다.
 */
export function needsOperatorCheckToEdit(
  post: Pick<Post, 'authorId'>,
  board: Pick<Board, 'writePolicy'>,
  userId: string,
): boolean {
  return isOperatorOnly(board) && isAuthor(post, userId);
}

/**
 * 이 글을 지워도 되는가. 글쓴이와 운영자다.
 * 운영자만 쓰는 게시판의 글은 운영자만 지운다. 글쓴이여도 지금 운영자가 아니면 지우지 못한다.
 */
export function canDelete(
  post: Pick<Post, 'authorId'>,
  board: Pick<Board, 'writePolicy'>,
  userId: string,
  isOperator: boolean,
): boolean {
  if (isOperatorOnly(board)) {
    return isOperator;
  }
  return isAuthor(post, userId) || isOperator;
}

/**
 * 지워도 되는지 알려면 운영자인지를 DB 에 물어야 하는가.
 * 누구나 쓰는 게시판의 제 글이면 묻지 않는다. 글쓴이는 운영자가 아니어도 지운다.
 */
export function needsOperatorCheckToDelete(
  post: Pick<Post, 'authorId'>,
  board: Pick<Board, 'writePolicy'>,
  userId: string,
): boolean {
  return isOperatorOnly(board) || !isAuthor(post, userId);
}
