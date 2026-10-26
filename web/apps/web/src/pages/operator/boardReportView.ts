// web/apps/web/src/pages/operator/boardReportView.ts
// 게시판의 신고(E4)를 보일 말. 순수한 함수다. 사유는 게시판 서버의 다섯 가지다(미성년 사유가 없다).

import type { BoardReport, BoardReportOutcome, BoardReportTarget } from '../../api/boardReports';

const REASONS = ['spam', 'abuse', 'sexual', 'illegal', 'other'] as const;

export const BOARD_REASON_LABELS: Record<(typeof REASONS)[number], string> = {
  spam: '스팸·광고',
  abuse: '욕설·괴롭힘',
  sexual: '음란물',
  illegal: '불법 정보',
  other: '기타',
};

const OUTCOME_LABELS: Record<BoardReportOutcome, string> = {
  actioned: '조치함',
  dismissed: '문제없음',
};

export function boardReasonLabel(reason: string): string {
  return (BOARD_REASON_LABELS as Record<string, string>)[reason] ?? reason;
}

/** 사유마다의 수를 한 줄로. 0 은 뺀다 */
export function boardReasonSummary(reasons: Record<string, number>): string {
  return REASONS.filter((reason) => (reasons[reason] ?? 0) > 0)
    .map((reason) => `${BOARD_REASON_LABELS[reason]} ${reasons[reason]}`)
    .join(' · ');
}

/** 처리한 결과. 아직이면 "열림" */
export function boardOutcomeLabel(report: Pick<BoardReport, 'outcome'>): string {
  return report.outcome ? OUTCOME_LABELS[report.outcome] : '열림';
}

/** 신고당한 것의 이름. "글 12", "글 12 의 댓글 57" */
export function targetLabel(target: BoardReportTarget): string {
  return target.type === 'post' ? `글 ${target.id}` : `글 ${target.post_id} 의 댓글 ${target.id}`;
}

/** 그 글로 가는 주소. 지운 글은 열리지 않으므로 null(댓글만 지웠으면 글은 열린다) */
export function targetPostPath(target: BoardReportTarget): string | null {
  if (target.deleted && target.type === 'post') return null;
  return `/board/posts/${encodeURIComponent(target.post_id)}`;
}
