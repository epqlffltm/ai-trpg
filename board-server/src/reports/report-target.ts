// board-server/src/reports/report-target.ts

/**
 * 신고하는 것(글이나 댓글)을 가리키는 값. 순수한 함수들이다.
 *
 * 글과 댓글은 같은 길(신고하기, 읽기, 처리하기)을 걷는다. 다른 것은 어느 칸(post_id, comment_id)을 보느냐뿐이다.
 * 그 차이를 이 파일에 모은다. 서비스는 종류를 가리지 않고 이 값을 넘긴다.
 */

/** 신고하는 것의 종류 */
export type ReportTargetType = 'post' | 'comment';

/** 신고하는 것. 종류와 번호다. */
export interface ReportTarget {
  type: ReportTargetType;
  id: string;
}

/** 글을 가리킨다. */
export function postTarget(id: string): ReportTarget {
  return { type: 'post', id };
}

/** 댓글을 가리킨다. */
export function commentTarget(id: string): ReportTarget {
  return { type: 'comment', id };
}

/** 신고의 두 칸에 적을 값. 꼭 하나만 찬다. */
export interface TargetColumns {
  postId: string | null;
  commentId: string | null;
}

/** 이것을 가리키는 신고의 두 칸. 새 신고에 적고, 이것의 신고를 찾을 때 조건으로 쓴다. */
export function targetColumns(target: ReportTarget): TargetColumns {
  return target.type === 'post'
    ? { postId: target.id, commentId: null }
    : { postId: null, commentId: target.id };
}

/** 이것의 신고를 찾는 조건. 비어 있는 칸은 조건에 넣지 않는다. */
export function whereTarget(
  target: ReportTarget,
): { postId: string } | { commentId: string } {
  return target.type === 'post'
    ? { postId: target.id }
    : { commentId: target.id };
}

/** 신고의 두 칸에서 무엇을 가리키는지 읽는다. 둘 다 비어 있는 행은 DB 가 막는다. */
export function targetOf(columns: TargetColumns): ReportTarget {
  if (columns.postId !== null) {
    return postTarget(columns.postId);
  }
  if (columns.commentId !== null) {
    return commentTarget(columns.commentId);
  }
  throw new Error('신고가 글도 댓글도 가리키지 않는다');
}
