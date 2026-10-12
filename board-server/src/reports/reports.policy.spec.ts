// board-server/src/reports/reports.policy.spec.ts

/**
 * 신고의 규칙(reports.policy.ts)을 검증한다.
 */

import {
  canReport,
  DESCRIPTION_MAX_LENGTH,
  needsDescription,
  REPORT_OUTCOMES,
  REPORT_REASONS,
  sqlList,
} from './reports.policy.js';

const ME = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const SOMEONE = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';

describe('정해 둔 값', () => {
  it('사유는 다섯, 처리 결과는 둘이다', () => {
    expect(REPORT_REASONS).toEqual([
      'spam',
      'abuse',
      'sexual',
      'illegal',
      'other',
    ]);
    expect(REPORT_OUTCOMES).toEqual(['actioned', 'dismissed']);
  });

  it('설명은 500자까지다', () => {
    expect(DESCRIPTION_MAX_LENGTH).toBe(500);
  });
});

describe('needsDescription', () => {
  it('기타만 설명을 꼭 적는다', () => {
    expect(needsDescription('other')).toBe(true);
  });

  it.each(['spam', 'abuse', 'sexual', 'illegal', undefined, 'OTHER'])(
    '%s 는 적지 않아도 된다',
    (reason) => {
      expect(needsDescription(reason)).toBe(false);
    },
  );
});

describe('canReport', () => {
  it('남이 쓴 것은 신고한다', () => {
    expect(canReport(SOMEONE, ME)).toBe(true);
  });

  it('자기가 쓴 것은 신고하지 못한다', () => {
    expect(canReport(ME, ME)).toBe(false);
  });
});

describe('sqlList', () => {
  it('값마다 따옴표를 붙여 쉼표로 잇는다', () => {
    expect(sqlList(['a', 'b'])).toBe("'a', 'b'");
  });
});
