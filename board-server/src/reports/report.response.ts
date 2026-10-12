// board-server/src/reports/report.response.ts

/**
 * 신고를 응답의 모양으로 바꾼다. 순수한 함수들이다.
 *
 * 칸 이름은 밑줄로 잇고, 번호는 글자로 내보낸다. 글, 댓글과 같다.
 * 신고한 사람에게는 접수했다는 것만 돌려준다. 누가 무엇을 신고했는지(설명, 신고한 사람)는 운영자의 응답에만 싣는다.
 */

import { OpenReportGroup, ReasonCounts } from './open-groups.js';
import { Report } from './report.entity.js';
import { ReportTarget, ReportTargetType } from './report-target.js';
// 타입만 가져온다(import type)
import type { ReportOutcome, ReportReason } from './reports.policy.js';

/** 신고한 사람에게 돌려주는 것. 접수했다는 표시다. */
export interface ReportReceiptResponse {
  id: string;
  reason: ReportReason;
  created_at: string;
}

/** 운영자가 읽는 신고 한 건. */
export interface ReportResponse {
  id: string;
  reason: ReportReason;
  /** 신고한 사람이 붙인 설명. 적지 않았으면 null */
  description: string | null;
  /** 신고한 사람. 인증 서버의 public_id */
  reporter_id: string;
  created_at: string;
  /** 처리한 시각. 열린 신고면 null */
  handled_at: string | null;
  /** 처리한 운영자. 열린 신고면 null */
  handled_by: string | null;
  /** 처리한 결과. 열린 신고면 null */
  outcome: ReportOutcome | null;
}

/** 신고당한 것. 운영자의 목록에서 무엇에 걸린 신고인지 보여 준다. */
export interface ReportTargetResponse {
  type: ReportTargetType;
  id: string;
  /** 글이면 그 글의 번호, 댓글이면 그 댓글이 달린 글의 번호 */
  post_id: string;
  /** 지금 지워져 있는가. 지운 것에 걸린 신고도 처리해서 닫아야 목록에서 빠진다 */
  deleted: boolean;
}

/** 운영자의 목록 한 줄. 신고당한 것 하나에 걸린 열린 신고들이다. */
export interface OpenReportGroupResponse {
  target: ReportTargetResponse;
  open_count: number;
  reasons: ReasonCounts;
  first_reported_at: string;
  last_reported_at: string;
}

/** 신고당한 것의 지금 상태. 신고의 칸이 아니어서 따로 읽어 넘긴다. */
export interface TargetState {
  /** 글이면 그 글의 번호, 댓글이면 그 댓글이 달린 글의 번호 */
  postId: string;
  deleted: boolean;
}

export function toReportReceiptResponse(
  report: Pick<Report, 'id' | 'reason' | 'createdAt'>,
): ReportReceiptResponse {
  return {
    id: report.id,
    reason: report.reason,
    created_at: report.createdAt.toISOString(),
  };
}

export function toReportResponse(report: Report): ReportResponse {
  return {
    id: report.id,
    reason: report.reason,
    description: report.description,
    reporter_id: report.reporterId,
    created_at: report.createdAt.toISOString(),
    handled_at: report.handledAt?.toISOString() ?? null,
    handled_by: report.handledBy,
    outcome: report.outcome,
  };
}

export function toReportTargetResponse(
  target: ReportTarget,
  state: TargetState,
): ReportTargetResponse {
  return {
    type: target.type,
    id: target.id,
    post_id: state.postId,
    deleted: state.deleted,
  };
}

export function toOpenReportGroupResponse(
  group: OpenReportGroup,
  state: TargetState,
): OpenReportGroupResponse {
  return {
    target: toReportTargetResponse(group.target, state),
    open_count: group.openCount,
    reasons: group.reasons,
    first_reported_at: group.firstReportedAt.toISOString(),
    last_reported_at: group.lastReportedAt.toISOString(),
  };
}
