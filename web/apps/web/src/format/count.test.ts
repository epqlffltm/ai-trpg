// web/apps/web/src/format/count.test.ts
// 수를 짧게 쓰기(#985).

import { describe, expect, it } from 'vitest';
import { compactCount } from './count';

describe('compactCount', () => {
  it('1,000 아래는 그대로, 그 위는 K 와 M 으로 소수 한 자리까지 쓴다', () => {
    expect(compactCount(0)).toBe('0');
    expect(compactCount(999)).toBe('999');
    expect(compactCount(1000)).toBe('1K');
    expect(compactCount(12_345)).toBe('12.3K');
    expect(compactCount(2_500_000)).toBe('2.5M');
  });
});
