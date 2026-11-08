// web/apps/web/src/layout/accountMenuView.test.ts
// 프로필 메뉴의 "다음 출석까지". 출석의 날짜는 한국 날짜라 서버가 준 오늘의 다음 날 0시(+09:00)까지 남은 때다.

import { describe, expect, it } from 'vitest';
import { untilNextAttendance } from './accountMenuView';

describe('다음 출석까지', () => {
  it('한국 날짜의 다음 날 0시까지 시·분·초', () => {
    // 한국 시각 2026-11-09 19:05:42 는 UTC 10:05:42
    expect(untilNextAttendance('2026-11-09', Date.parse('2026-11-09T10:05:42Z'))).toBe('04:54:18');
    // 한국 시각 0시 직후
    expect(untilNextAttendance('2026-11-09', Date.parse('2026-11-08T15:00:01Z'))).toBe('23:59:59');
  });

  it('지났거나 날짜를 읽지 못하면 없다', () => {
    expect(untilNextAttendance('2026-11-09', Date.parse('2026-11-09T15:00:00Z'))).toBeNull();
    expect(untilNextAttendance('어제', Date.now())).toBeNull();
  });
});
