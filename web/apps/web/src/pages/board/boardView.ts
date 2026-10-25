// web/apps/web/src/pages/board/boardView.ts
// 공지·게시판(A11)이 보일 글과 주소의 값. 순수한 함수다.
// 검색어의 규칙은 게시판 서버(board-server/app/posts/terms.py)와 같다: 낱말 2자 이상, 5개까지, 전체 50자.

import type { BoardComment, PostSummary } from '../../api/types';

type Author = Pick<PostSummary, 'author_nickname' | 'author_withdrawn'>;

export const MIN_TERM_LENGTH = 2;
export const MAX_TERMS = 5;
export const MAX_QUERY_LENGTH = 50;
/** 서버가 받는 가장 큰 쪽 번호 */
const MAX_PAGE = 10_000;

/** 글쓴이의 이름. 탈퇴했으면 "탈퇴한 사용자", 서버가 이름을 모르면 "알 수 없음" */
export function authorName(author: Author): string {
  if (author.author_withdrawn) return '탈퇴한 사용자';
  return author.author_nickname ?? '알 수 없음';
}

/** 지운 댓글(답글이 있어 자리만 남음)의 글 */
export function commentText(comment: Pick<BoardComment, 'deleted' | 'content'>): string {
  return comment.deleted ? '삭제된 댓글입니다' : (comment.content ?? '');
}

/** 주소의 page 값을 쪽 번호로. 틀리면 1 */
export function parsePage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page >= 1 ? Math.min(page, MAX_PAGE) : 1;
}

/** 모두 몇 쪽인가. 글이 없어도 1 */
export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, size)));
}

/** 서버처럼 낱말로 나눈 검색어. 이어진 빈칸은 하나로, 같은 낱말은 한 번 */
export function normalizeQuery(q: string): string {
  return [...new Set(q.split(/\s+/).filter((term) => term !== ''))].join(' ');
}

/** 검색어의 문제. 없으면 null. 빈 검색어는 문제가 아니라 아직 찾지 않은 것이다 */
export function searchHint(q: string): string | null {
  const query = normalizeQuery(q);
  if (query === '') return null;
  const terms = query.split(' ');
  if (terms.some((term) => [...term].length < MIN_TERM_LENGTH)) return `낱말마다 ${MIN_TERM_LENGTH}자 이상으로 적어 주세요.`;
  if (terms.length > MAX_TERMS) return `낱말은 ${MAX_TERMS}개까지입니다.`;
  return [...query].length > MAX_QUERY_LENGTH ? `검색어는 ${MAX_QUERY_LENGTH}자까지입니다.` : null;
}

/** 검색 화면의 주소. 게시판을 비우면 모든 게시판에서 찾는다 */
export function searchPath(q: string, board?: string): string {
  const params = new URLSearchParams({ q: normalizeQuery(q) });
  if (board) params.set('board', board);
  return `/board/search?${params.toString()}`;
}

/** 고쳐 쓴 글인가(만든 때와 고친 때가 다르다) */
export function isEdited(item: { created_at: string; updated_at: string }): boolean {
  return item.updated_at !== item.created_at;
}
