// board-server/src/reports/reports.policy.ts

/**
 * 신고의 규칙. DB 도 Nest 도 모르는 순수한 값과 함수들이다.
 *
 *   - 사유는 정해 둔 다섯 가운데 하나다. 운영자가 사유별로 세고 거를 수 있다.
 *     기타(other)를 고르면 설명을 꼭 적는다. "기타"만으로는 무엇이 문제인지 알 수 없다.
 *   - 자기 글과 자기 댓글은 신고하지 못한다. 쓸모가 없고 운영자의 목록만 어지럽힌다.
 *   - 같은 사람이 같은 것을 두 번 신고하지 못한다(DB 의 유일 제약이 지킨다).
 *   - 신고를 읽고 처리하는 것은 운영자만 한다. 누가 신고했는지는 운영자만 안다.
 *   - 신고가 쌓여도 저절로 가리지 않는다. 여럿이 짜고 멀쩡한 글을 가릴 수 있다. 사람이 본다.
 */

/** 신고의 사유. 스팸·광고, 욕설·괴롭힘, 음란물, 불법 정보, 기타 */
export const REPORT_REASONS = [
  'spam',
  'abuse',
  'sexual',
  'illegal',
  'other',
] as const;

export type ReportReason = (typeof REPORT_REASONS)[number];

/** 운영자가 처리한 결과. 조치함(글을 지우는 등), 문제없음 */
export const REPORT_OUTCOMES = ['actioned', 'dismissed'] as const;

export type ReportOutcome = (typeof REPORT_OUTCOMES)[number];

/** 설명의 최대 길이(글자) */
export const DESCRIPTION_MAX_LENGTH = 500;

/** 이 사유면 설명을 꼭 적어야 하는가. */
export function needsDescription(reason: unknown): boolean {
  return reason === 'other';
}

/** 이 사람이 이것(글이나 댓글)을 신고해도 되는가. 자기가 쓴 것은 안 된다. 글쓴이가 탈퇴한 것(null)은 누구나 신고한다. */
export function canReport(
  authorId: string | null,
  reporterId: string,
): boolean {
  return authorId !== reporterId;
}

/** 값들을 SQL 의 IN 목록으로 적는다. 정해 둔 상수에만 쓴다. 받은 값을 넣지 않는다. */
export function sqlList(values: readonly string[]): string {
  return values.map((value) => `'${value}'`).join(', ');
}
