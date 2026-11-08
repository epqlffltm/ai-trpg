// web/apps/web/src/pages/trpg/studio/rulebooks/injuryStatus.test.ts
// 짧은 부상(상태 이상)의 라운드마다의 피해와 벗어나기(#254)의 입력(injuryStatusForm.ts). 순수한 함수다.

import { describe, expect, it } from 'vitest';
import type { Injury } from '../../../../api/types';
import { magnitudeLabel, statusDraft, toInjuries, withRow, type StatusRules } from './injuryStatusForm';

const BLEEDING = { key: 'bleeding', name: '출혈', fact: '피가 흐른다.', effects: [], healing: 'rounds', rounds: 3, damage: { magnitude: 'light', nature: null }, escape: null } as unknown as Injury;
const SCAR = { key: 'deep_scar', name: '깊은 흉터', fact: '흉터가 남았다.', effects: [], healing: 'permanent', damage: null, escape: null } as unknown as Injury;
const RULES = {
  injuries: [BLEEDING, SCAR],
  magnitudes: [{ key: 'light', name: '가벼운 피해', count: 1, sides: 4 }, { key: 'heavy', name: '큰 피해', count: 2, sides: 8 }],
  natures: [],
  abilities: [],
  difficulties: [],
} as unknown as StatusRules;

describe('상태 이상의 입력', () => {
  it('짧은 부상만 줄이 되고, 받은 피해와 벗어나기를 칸에 채운다', () => {
    expect(statusDraft(RULES).rows).toEqual([{ key: 'bleeding', name: '출혈', magnitude: 'light', nature: '', ability: '', difficulty: '' }]);
  });

  it('피해를 비우면 성질도 비우고, 보낼 때는 짧은 것에만 칸을 싣는다', () => {
    const draft = withRow(withRow(statusDraft(RULES), 'bleeding', { nature: 'poison' }), 'bleeding', { magnitude: '' });

    expect(draft.rows[0]).toMatchObject({ magnitude: '', nature: '' });
    expect(toInjuries(draft)).toEqual([{ ...BLEEDING, damage: null, escape: null }, SCAR]);
  });

  it('벗어나기는 능력치를 고르면 싣고, 난이도를 비우면 기본 난이도(null)다', () => {
    const draft = withRow(statusDraft(RULES), 'bleeding', { ability: 'con' });

    expect(toInjuries(draft)[0]).toMatchObject({ damage: { magnitude: 'light', nature: null }, escape: { ability: 'con', difficulty: null } });
  });

  it('피해 등급은 이름과 주사위로 보인다', () => {
    expect(RULES.magnitudes.map(magnitudeLabel)).toEqual(['가벼운 피해(d4)', '큰 피해(2d8)']);
  });
});
