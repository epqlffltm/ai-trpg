// web/apps/web/src/components/ReferencesToggle.test.ts
// 참고 자료 켜기를 바꾸지 못한 까닭(describeReferencesProblem, #1338). 순수한 함수.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../api/errors';
import { describeReferencesProblem } from './ReferencesToggle';

describe('참고 자료 켜기의 까닭', () => {
  it('허용하지 않음, 너무 잦음, 연결, 그 밖을 가른다', () => {
    expect(describeReferencesProblem(new ApiError({ status: 422, detail: '안 된다', code: 'references_not_allowed' }))).toBe('만든 사람이 참고 자료를 허용하지 않았습니다.');
    expect(describeReferencesProblem(new ApiError({ status: 429, detail: '많다', code: 'too_many_attempts', retryAfter: 7 }))).toBe('너무 자주 바꿨습니다. 7초 뒤에 다시 해 주세요.');
    expect(describeReferencesProblem(new NetworkError(new Error('x')))).toMatch(/닿지 못했습니다/);
    expect(describeReferencesProblem(new Error('x'))).toBe('참고 자료를 바꾸지 못했습니다. 잠시 뒤에 다시 시도하세요.');
  });
});
