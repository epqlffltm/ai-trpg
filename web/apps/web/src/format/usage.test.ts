// web/apps/web/src/format/usage.test.ts
// 카드의 쓰인 수와 관심의 수(#985, #989).

import { describe, expect, it } from 'vitest';
import { usageTags } from './usage';

describe('usageTags', () => {
  it('0 이나 없는 수는 싣지 않고, 나머지는 짧게 쓴다', () => {
    expect(usageTags('대화', 12_345, 12)).toEqual(['대화 12.3K', '♥ 12']);
    expect(usageTags('테이블', 0, 3)).toEqual(['♥ 3']);
    expect(usageTags('이야기', undefined, undefined)).toEqual([]);
  });
});
