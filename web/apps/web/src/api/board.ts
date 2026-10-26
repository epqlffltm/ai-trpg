// web/apps/web/src/api/board.ts
// 공지·게시판(게시판 서버, A11)의 읽기. 게시판, 글 목록(쪽 번호), 글, 댓글("다음 몇 개"), 검색. 로그인하지 않아도 읽는다.
// 글쓴이가 탈퇴했으면 author_withdrawn 이 참이고 이름과 id 가 null 이다. 지운 댓글에 답글이 있으면 자리만 남는다(deleted).
// 실패: 404(없거나 지운 글, 없는 게시판), 400(검색어의 규칙, errors), 503(검색이 3초를 넘김, 공개키를 구할 수 없음 Retry-After).
// 쓰기(글, 댓글, 답글, 신고, 운영자의 고정)는 로그인해야 한다. 내가 누구인지와 운영자인지는 /board/me 가 안다(토큰에 없다).
// 쓰기의 실패: 401, 403(운영자 게시판, 남의 것, 자기 것을 신고), 404, 409(답글 100개, 고정 5개, 이미 신고), 429(retry_after), 400(errors).
// 403·404·409 의 detail 은 화면에 그대로 보일 문장이다(board-server/README.md 의 "오류").

import { apiRequest } from './http';
import type {
  Board,
  BoardComment,
  BoardMe,
  BoardReportCreate,
  BoardReportReceipt,
  CommentCreate,
  CommentList,
  Post,
  PostCreate,
  PostList,
  PostSummaryPage,
  PostUpdate,
} from './types';

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

/** 이 서버가 아는 나(user_id, is_operator). 로그인해야 부른다 */
export function fetchBoardMe(signal?: AbortSignal): Promise<BoardMe> {
  return apiRequest<BoardMe>(`${BOARD}/me`, withSignal(signal));
}

export function createPost(slug: string, body: PostCreate): Promise<Post> {
  return apiRequest<Post>(`${BOARD}/boards/${encodeURIComponent(slug)}/posts`, { method: 'POST', body });
}

/** 보낸 칸만 고친다 */
export function updatePost(id: string, body: PostUpdate): Promise<Post> {
  return apiRequest<Post>(`${BOARD}/posts/${encodeURIComponent(id)}`, { method: 'PATCH', body });
}

export function deletePost(id: string): Promise<void> {
  return apiRequest<void>(`${BOARD}/posts/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** 운영자의 고정. days 일 뒤에 저절로 내려간다. 이미 고정한 글이면 기간을 새로 잡는다 */
export function pinPost(id: string, days: number): Promise<void> {
  return apiRequest<void>(`${BOARD}/posts/${encodeURIComponent(id)}/pin`, { method: 'PUT', body: { days } });
}

export function unpinPost(id: string): Promise<void> {
  return apiRequest<void>(`${BOARD}/posts/${encodeURIComponent(id)}/pin`, { method: 'DELETE' });
}

/** 댓글. parent_id 가 있으면 그 댓글의 답글이다(답글에는 달지 못한다) */
export function createComment(postId: string, body: CommentCreate): Promise<BoardComment> {
  return apiRequest<BoardComment>(`${BOARD}/posts/${encodeURIComponent(postId)}/comments`, { method: 'POST', body });
}

export function updateComment(id: string, content: string): Promise<BoardComment> {
  return apiRequest<BoardComment>(`${BOARD}/comments/${encodeURIComponent(id)}`, { method: 'PATCH', body: { content } });
}

export function deleteComment(id: string): Promise<void> {
  return apiRequest<void>(`${BOARD}/comments/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export type ReportTarget = { kind: 'post' | 'comment'; id: string };

/** 남의 글이나 댓글의 신고. 접수했다는 것만 돌아온다 */
export function reportBoardItem(target: ReportTarget, body: BoardReportCreate): Promise<BoardReportReceipt> {
  const base = target.kind === 'post' ? 'posts' : 'comments';
  return apiRequest<BoardReportReceipt>(`${BOARD}/${base}/${encodeURIComponent(target.id)}/reports`, { method: 'POST', body });
}
