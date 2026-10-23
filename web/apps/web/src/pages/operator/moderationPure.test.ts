// web/apps/web/src/pages/operator/moderationPure.test.ts
// 신고 처리(E4)의 순수한 함수와 실패의 말.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../../api/errors';
import { describeModerationProblem } from './moderationProblem';
import { nextOffset, outcomeLabel, PAGE_SIZE, reasonLabel, reasonProblem, reasonSummary, speakerLabel } from './moderationPure';

function apiError(status: number, code?: string) {
  return new ApiError({ status, detail: '실패', code });
}

describe('신고 처리의 말', () => {
  it('사유마다의 수는 0 을 빼고 미성년부터 한 줄이다', () => {
    expect(reasonSummary({ spam: 2, abuse: 0, minor: 1, other: 3 })).toBe('미성년 인물을 성적으로 1 · 스팸·광고 2 · 기타 3');
    expect(reasonSummary({})).toBe('');
  });

  it('사유와 처리를 화면의 말로', () => {
    expect(reasonLabel('illegal')).toBe('불법');
    expect([outcomeLabel(null), outcomeLabel('actioned'), outcomeLabel('dismissed')]).toEqual(['열림', '받아들임', '기각']);
  });

  it('운영자의 사유는 빈칸을 빼고 1~200자다', () => {
    expect(reasonProblem('   ')).toMatch(/적어 주세요/);
    expect(reasonProblem(` ${'가'.repeat(200)} `)).toBeNull();
    expect(reasonProblem('가'.repeat(201))).toMatch(/200자/);
  });

  it('다음 쪽은 다 읽기 전까지만', () => {
    expect(nextOffset(PAGE_SIZE + 1, 1)).toBe(PAGE_SIZE);
    expect(nextOffset(PAGE_SIZE, 1)).toBeUndefined();
  });

  it('굳힌 말을 한 사람', () => {
    expect([speakerLabel('user', '세라'), speakerLabel('assistant', '세라'), speakerLabel('system', '세라')]).toEqual([
      '사람',
      '세라',
      'system',
    ]);
  });
});

describe('신고 처리의 실패', () => {
  it('없거나 이미 처리했으면 목록을 다시 읽는다', () => {
    expect(describeModerationProblem(apiError(404))).toMatchObject({ refresh: true, message: expect.stringMatching(/찾을 수 없습니다/) });
    expect(describeModerationProblem(apiError(409, 'already_handled'))).toMatchObject({
      refresh: true,
      message: expect.stringMatching(/이미 처리한/),
    });
  });

  it('받지 않는 값, 닿지 못함, 모르는 실패', () => {
    expect(describeModerationProblem(apiError(422)).refresh).toBeUndefined();
    expect(describeModerationProblem(new NetworkError(new Error('down'))).message).toMatch(/닿지 못했습니다/);
    expect(describeModerationProblem(apiError(500)).message).toMatch(/처리하지 못했습니다/);
    expect(describeModerationProblem('boom').message).toMatch(/처리하지 못했습니다/);
  });
});
