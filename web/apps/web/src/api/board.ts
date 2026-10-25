// web/apps/web/src/api/board.ts
// 공지·게시판(게시판 서버, A11)의 읽기. 게시판, 글 목록(쪽 번호), 글, 댓글("다음 몇 개"), 검색. 로그인하지 않아도 읽는다.
// 글쓴이가 탈퇴했으면 author_withdrawn 이 참이고 이름과 id 가 null 이다. 지운 댓글에 답글이 있으면 자리만 남는다(deleted).
// 실패: 404(없거나 지운 글, 없는 게시판), 400(검색어의 규칙, errors), 503(검색이 3초를 넘김, 공개키를 구할 수 없음 Retry-After).
// 쓰기(글, 댓글, 신고)는 다음에 더한다.

import { apiRequest } from './http';
import type { Board, CommentList, Post, PostList, PostSummaryPage } from './types';

const BOARD = '/api/v1/board';

/** 한 쪽에 보일 글 수(서버는 1~50) */
export const POST_PAGE_SIZE = 20;
/** 한 번에 읽는 댓글 수 */
export const COMMENT_PAGE_SIZE = 50;

function withSignal(signal?: AbortSignal) {
  return signal ? { signal } : {};
}

export function fetchBoards(signal?: AbortSignal): Promise<Board[]> {
  return apiRequest<Board[]>(`${BOARD}/boards`, withSignal(signal));
}

/** 게시판의 한 쪽. 첫 쪽에만 고정한 글(pinned)이 따로 온다 */
export function fetchBoardPosts(slug: string, page: number, signal?: AbortSignal): Promise<PostList> {
  return apiRequest<PostList>(`${BOARD}/boards/${encodeURIComponent(slug)}/posts`, { query: { page, size: POST_PAGE_SIZE }, ...withSignal(signal) });
}

export function fetchPost(id: string, signal?: AbortSignal): Promise<Post> {
  return apiRequest<Post>(`${BOARD}/posts/${encodeURIComponent(id)}`, withSignal(signal));
}

/** 댓글(답글을 품은). after 는 앞 묶음의 next(첫 묶음이면 비운다) */
export function fetchComments(postId: string, after: string | undefined, signal?: AbortSignal): Promise<CommentList> {
  return apiRequest<CommentList>(`${BOARD}/posts/${encodeURIComponent(postId)}/comments`, { query: { after, size: COMMENT_PAGE_SIZE }, ...withSignal(signal) });
}

/** 제목과 본문에서 모든 낱말이 들어 있는 글. board 를 비우면 모든 게시판. 새 글부터 */
export function searchPosts(q: string, board: string | undefined, page: number, signal?: AbortSignal): Promise<PostSummaryPage> {
  return apiRequest<PostSummaryPage>(`${BOARD}/posts`, { query: { q, board, page, size: POST_PAGE_SIZE }, ...withSignal(signal) });
}
