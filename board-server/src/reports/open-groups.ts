// board-server/src/reports/open-groups.ts

/**
 * 열린 신고를 신고당한 것(글이나 댓글)마다 묶은 것. 운영자의 목록 한 줄이다. 순수한 함수들이다.
 *
 * 한 글에 일곱 명이 신고하면 운영자가 볼 것은 하나다. 일곱 줄이 아니라 한 줄로 묶고,
 * 몇 건인지, 사유별로 몇 건인지, 처음과 마지막 신고가 언제인지를 함께 싣는다.
 * 묶는 셈은 DB 가 한다(GROUP BY). 여기서는 DB 가 준 줄을 읽기 좋은 모양으로 바꾼다.
 */

import { ReportTarget, targetOf } from './report-target.js';
import { REPORT_REASONS } from './reports.policy.js';
// 타입만 가져온다(import type)
import type { ReportReason } from './reports.policy.js';

/** 사유마다의 건수 */
export type ReasonCounts = Record<ReportReason, number>;

/** 신고당한 것 하나에 걸린 열린 신고들. */
export interface OpenReportGroup {
  target: ReportTarget;
  /** 열린 신고의 수 */
  openCount: number;
  /** 사유마다의 수 */
  reasons: ReasonCounts;
  firstReportedAt: Date;
  lastReportedAt: Date;
}

/** 사유 하나의 건수를 담는 칸의 이름. 쿼리와 읽는 곳이 같은 이름을 쓴다 */
export function reasonColumn(reason: ReportReason): string {
  return `reason_${reason}`;
}

/**
 * DB 가 준 한 줄. 번호와 건수는 글자로 온다(bigint).
 * 사유마다의 건수는 reasonColumn 의 이름으로 온다.
 */
export interface OpenGroupRow {
  post_id: string | null;
  comment_id: string | null;
  open_count: string;
  first_reported_at: Date;
  last_reported_at: Date;
  [reasonCount: string]: string | Date | null;
}

/** 사유마다의 건수를 읽는다. 없는 칸은 0 이다. */
export function reasonCountsOf(row: OpenGroupRow): ReasonCounts {
  const counts = {} as ReasonCounts;
  for (const reason of REPORT_REASONS) {
    counts[reason] = Number(row[reasonColumn(reason)] ?? 0);
  }
  return counts;
}

/** DB 가 준 한 줄을 묶음으로 바꾼다. */
export function openGroupOf(row: OpenGroupRow): OpenReportGroup {
  return {
    target: targetOf({ postId: row.post_id, commentId: row.comment_id }),
    openCount: Number(row.open_count),
    reasons: reasonCountsOf(row),
    firstReportedAt: row.first_reported_at,
    lastReportedAt: row.last_reported_at,
  };
}
