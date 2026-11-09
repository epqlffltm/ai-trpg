// web/apps/web/src/pages/trpg/studio/scenarios/defendsForm.test.ts
// 몬스터와 인물 시트의 방어하는 때(#254)의 입력. 비우면 보내지 않고, 칸마다 범위를 본다.

import { describe, expect, it } from 'vitest';
import { defendsDraft, defendsHints, defendsLine, hasDefendsHints, toDefends } from './defendsForm';

describe('방어하는 때의 입력', () => {
  it('둘 다 비우면 방어하지 않는다(null). 받은 값은 그대로 돌아간다', () => {
    expect(toDefends(defendsDraft(null))).toBeNull();
    expect(toDefends({ below: '  ', chance: '' })).toBeNull();
    expect(toDefends(defendsDraft({ below: 30, chance: null }))).toEqual({ below: 30, chance: null });
    expect(toDefends(defendsDraft({ below: null, chance: 100 }))).toEqual({ below: null, chance: 100 });
  });

  it('문턱은 1~99, 확률은 1~100 의 정수다', () => {
    expect(hasDefendsHints(defendsHints({ below: '', chance: '' }))).toBe(false);
    expect(hasDefendsHints(defendsHints({ below: '99', chance: '100' }))).toBe(false);
    expect(defendsHints({ below: '100', chance: '0' })).toEqual({ below: '1~99 사이의 정수입니다.', chance: '1~100 사이의 정수입니다.' });
    expect(defendsHints({ below: '1.5', chance: '101' })).toEqual({ below: '1~99 사이의 정수입니다.', chance: '1~100 사이의 정수입니다.' });
  });

  it('목록의 줄', () => {
    expect(defendsLine(null)).toBeNull();
    expect(defendsLine({ below: 30, chance: 25 })).toBe('방어 HP 30% 이하, 25%');
    expect(defendsLine({ below: null, chance: 25 })).toBe('방어 25%');
  });
});
