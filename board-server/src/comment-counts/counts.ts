// board-server/src/comment-counts/counts.ts

/**
 * 글마다의 댓글 수를 다루는 셈. 순수한 함수들이다. DB 를 모른다.
 */

/** DB 가 돌려주는 한 줄. 글 번호와 그 글의 댓글 수다. 수는 글자로 온다(PostgreSQL 의 COUNT 는 bigint 다). */
export interface CountRow {
  postId: string;
  count: string;
}

/** 글 번호로 댓글 수를 찾는 표. 댓글이 없는 글은 들어 있지 않다. */
export type CommentCounts = ReadonlyMap<string, number>;

/** DB 가 돌려준 줄들을 글 번호로 찾는 표로 바꾼다. */
export function countsFrom(rows: readonly CountRow[]): CommentCounts {
  return new Map(rows.map((row) => [row.postId, Number(row.count)]));
}

/** 이 글의 댓글 수. 표에 없는 글은 댓글이 없는 글이다. */
export function countOf(counts: CommentCounts, postId: string): number {
  return counts.get(postId) ?? 0;
}
