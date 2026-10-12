// board-server/src/reports/open-groups.spec.ts

/**
 * 열린 신고의 묶음(open-groups.ts)을 검증한다. DB 가 주는 줄의 모양을 손으로 만들어 넣는다.
 */

import {
  OpenGroupRow,
  openGroupOf,
  reasonColumn,
  reasonCountsOf,
} from './open-groups.js';

const FIRST = new Date('2026-10-12T01:00:00Z');
const LAST = new Date('2026-10-12T02:00:00Z');

/** DB 가 주는 것과 같은 모양의 줄. 건수는 글자다. */
function row(overrides: Partial<OpenGroupRow> = {}): OpenGroupRow {
  return {
    post_id: '7',
    comment_id: null,
    open_count: '3',
    first_reported_at: FIRST,
    last_reported_at: LAST,
    reason_spam: '2',
    reason_abuse: '0',
    reason_sexual: '0',
    reason_illegal: '0',
    reason_other: '1',
    ...overrides,
  };
}

describe('reasonColumn', () => {
  it('사유 앞에 reason_ 을 붙인다', () => {
    expect(reasonColumn('spam')).toBe('reason_spam');
  });
});

describe('reasonCountsOf', () => {
  it('사유마다의 건수를 숫자로 읽는다', () => {
    expect(reasonCountsOf(row())).toEqual({
      spam: 2,
      abuse: 0,
      sexual: 0,
      illegal: 0,
      other: 1,
    });
  });

  it('없는 칸은 0 이다', () => {
    const { reason_other: _, ...rest } = row();
    expect(reasonCountsOf(rest as OpenGroupRow).other).toBe(0);
  });
});

describe('openGroupOf', () => {
  it('글의 묶음으로 읽는다', () => {
    expect(openGroupOf(row())).toEqual({
      target: { type: 'post', id: '7' },
      openCount: 3,
      reasons: { spam: 2, abuse: 0, sexual: 0, illegal: 0, other: 1 },
      firstReportedAt: FIRST,
      lastReportedAt: LAST,
    });
  });

  it('댓글의 묶음으로 읽는다', () => {
    const group = openGroupOf(row({ post_id: null, comment_id: '9' }));

    expect(group.target).toEqual({ type: 'comment', id: '9' });
  });
});
