// board-server/src/reports/report.response.spec.ts

/**
 * 신고를 응답의 모양으로 바꾸는 함수들(report.response.ts)을 검증한다.
 */

import { OpenReportGroup } from './open-groups.js';
import { Report } from './report.entity.js';
import {
  toOpenReportGroupResponse,
  toReportReceiptResponse,
  toReportResponse,
  toReportTargetResponse,
} from './report.response.js';
import { commentTarget } from './report-target.js';

const CREATED = new Date('2026-10-12T01:00:00Z');
const HANDLED = new Date('2026-10-12T03:00:00Z');
const REPORTER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const OPERATOR = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';

/** 신고 하나. 열린 신고다. */
function report(overrides: Partial<Report> = {}): Report {
  return Object.assign(new Report(), {
    id: '5',
    postId: '7',
    commentId: null,
    reporterId: REPORTER,
    reason: 'abuse',
    description: '설명',
    createdAt: CREATED,
    handledAt: null,
    handledBy: null,
    outcome: null,
    ...overrides,
  });
}

describe('toReportReceiptResponse', () => {
  it('번호, 사유, 시각만 싣는다. 설명과 신고한 사람은 싣지 않는다', () => {
    expect(toReportReceiptResponse(report())).toEqual({
      id: '5',
      reason: 'abuse',
      created_at: '2026-10-12T01:00:00.000Z',
    });
  });
});

describe('toReportResponse', () => {
  it('열린 신고는 처리한 칸들이 null 이다', () => {
    expect(toReportResponse(report())).toEqual({
      id: '5',
      reason: 'abuse',
      description: '설명',
      reporter_id: REPORTER,
      created_at: '2026-10-12T01:00:00.000Z',
      handled_at: null,
      handled_by: null,
      outcome: null,
    });
  });

  it('처리한 신고는 언제, 누가, 어떻게 처리했는지 싣는다', () => {
    const handled = report({
      handledAt: HANDLED,
      handledBy: OPERATOR,
      outcome: 'dismissed',
    });

    expect(toReportResponse(handled)).toMatchObject({
      handled_at: '2026-10-12T03:00:00.000Z',
      handled_by: OPERATOR,
      outcome: 'dismissed',
    });
  });
});

describe('toReportTargetResponse', () => {
  it('댓글이면 그 댓글이 달린 글의 번호를 함께 싣는다', () => {
    expect(
      toReportTargetResponse(commentTarget('9'), {
        postId: '7',
        deleted: true,
      }),
    ).toEqual({ type: 'comment', id: '9', post_id: '7', deleted: true });
  });
});

describe('toOpenReportGroupResponse', () => {
  it('묶음을 밑줄 이름과 글자 시각으로 바꾼다', () => {
    const group: OpenReportGroup = {
      target: commentTarget('9'),
      openCount: 2,
      reasons: { spam: 1, abuse: 1, sexual: 0, illegal: 0, other: 0 },
      firstReportedAt: CREATED,
      lastReportedAt: HANDLED,
    };

    expect(
      toOpenReportGroupResponse(group, { postId: '7', deleted: false }),
    ).toEqual({
      target: { type: 'comment', id: '9', post_id: '7', deleted: false },
      open_count: 2,
      reasons: { spam: 1, abuse: 1, sexual: 0, illegal: 0, other: 0 },
      first_reported_at: '2026-10-12T01:00:00.000Z',
      last_reported_at: '2026-10-12T03:00:00.000Z',
    });
  });
});
