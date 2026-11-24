// web/apps/web/src/pages/trpg/room/events/narrationFailure.test.ts
// 서술의 실패에 적힌 까닭(코드)을 사람이 읽는 말로 바꾸는지 본다. 코드를 그대로 보이지 않는다.

import { describe, expect, it } from 'vitest';
import { failureCause, failureText } from './narrationFailure';

describe('서술 실패의 까닭', () => {
  it('아는 코드는 까닭을 말한다', () => {
    expect(failureText('insufficient_credits')).toBe('크레딧이 모자라 서술하지 못했습니다.');
    expect(failureText('timeout')).toBe('모델이 제때 답하지 않아 서술하지 못했습니다.');
    expect(failureCause('status_503')).toBe('모델 쪽에 문제가 있어');
  });

  it('모르거나 없는 코드는 까닭 없이 실패만 말하고 코드를 보이지 않는다', () => {
    expect(failureText('status_418')).toBe('서술에 실패했습니다.');
    expect(failureText('error')).toBe('서술에 실패했습니다.');
    expect(failureText(null)).toBe('서술에 실패했습니다.');
    expect(failureText('constructor')).toBe('서술에 실패했습니다.');
  });
});
