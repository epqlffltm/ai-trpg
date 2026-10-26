// web/apps/web/src/pages/trpg/studio/rulebooks/resources.test.ts
// HP 말고 다른 수치(#804)의 화면 쪽 순수한 함수. 룰북의 수치 입력(resourcesForm.ts), 물건의 맞추기(itemEffectsForm.ts),
// 결과의 줄(actionOutcome.ts), 해로운 물건(actionOptions.ts 의 itemHarms)을 본다.

import { describe, expect, it } from 'vitest';
import type { Declaration, Resource, TableDetail } from '../../../../api/types';
import { tableDetail } from '../../../../test/tableFixtures';
import { itemHarms } from '../../room/round/action/actionOptions';
import { itemUseLine, restLine } from '../../room/round/actionOutcome';
import { adjustAmount, effectDraft, effectHints, effectLine, newEffectDraft, toEffect } from '../scenarios/itemEffectsForm';
import { newResourceDraft, resourceDraft, resourceHints, resourceLine, toResource } from './resourcesForm';

const MANA: Resource = {
  key: 'mana',
  name: '마나',
  min: 0,
  max: { base: 3, ability: 'heart', cap: 10 },
  start: 'max',
  rest: { short: { kind: 'raise', amount: 2 }, long: { kind: 'fill', amount: null } },
};

type Outcome = NonNullable<Declaration['outcome']>;

describe('룰북의 수치', () => {
  it('서버의 수치를 고칠 거리로 바꾸고 다시 보낼 모양으로 돌린다', () => {
    expect(toResource(resourceDraft(MANA))).toEqual(MANA);
  });

  it('새 줄은 쓰지 않은 이름표를 고른다', () => {
    const first = newResourceDraft([]);
    expect(first.key).toBe('resource');
    expect(newResourceDraft([first]).key).toBe('resource_2');
  });

  it('보내기 전에 이름표, 이름, 범위, 쉬기의 양, 겹침을 본다', () => {
    const draft = resourceDraft(MANA);
    expect(resourceHints([draft])).toEqual({});
    const broken = { ...draft, key: 'Mana', name: '', base: '0', ability: '', cap: '', short: { kind: 'raise' as const, amount: '' } };
    expect(Object.keys(resourceHints([broken])).sort()).toEqual(['resource.0.base', 'resource.0.key', 'resource.0.name', 'resource.0.short']);
    expect(resourceHints([draft, draft]).resources).toBe('같은 이름표의 수치가 두 번 있습니다.');
  });

  it('한 줄의 글', () => {
    expect(resourceLine(MANA, () => '마음')).toBe('마나 0~(3 + 마음, 10 까지) · 가득에서 시작 · 짧은 휴식 +2 · 긴 휴식 채우기');
  });
});

describe('물건의 맞추기', () => {
  it('수치와 양을 고르고, 0 과 범위 밖은 알린다', () => {
    const draft = { ...newEffectDraft('adjust'), resource: 'mana', amount: '-2' };
    expect(toEffect(draft)).toEqual({ kind: 'adjust', resource: 'mana', amount: -2 });
    expect(effectDraft({ kind: 'adjust', resource: 'mana', amount: 3 })).toMatchObject({ resource: 'mana', amount: '3' });
    expect(adjustAmount('-99')).toBe(-99);
    expect(adjustAmount('0')).toBeNull();
    expect(adjustAmount('100')).toBeNull();
    expect(effectHints([{ ...draft, amount: '0' }])['effect.0']).toContain('0 이 아닌');
    expect(effectHints([draft, draft]).effects).toBe('같은 수치를 두 번 맞춥니다.');
    expect(effectLine({ kind: 'adjust', resource: 'mana', amount: 3 }, { resources: [MANA] } as never)).toBe('마나 +3');
  });

  it('수치를 내리는 물건은 해롭다', () => {
    const table = tableDetail('t', {
      items: [
        { entry_id: 'up', name: '물약', kind: 'consumable', rarity: 'normal', effects: [{ kind: 'adjust', resource: 'mana', amount: 3 }], aids: [] },
        { entry_id: 'down', name: '책', kind: 'consumable', rarity: 'normal', effects: [{ kind: 'adjust', resource: 'mana', amount: -2 }], aids: [] },
      ],
    }) as unknown as TableDetail;
    expect(itemHarms(table, 'up')).toBe(false);
    expect(itemHarms(table, 'down')).toBe(true);
  });
});

describe('결과의 줄', () => {
  it('쉬기와 물건이 바꾼 수치를 붙인다', () => {
    const mana = { resource: 'mana', name: '마나', before: 1, after: 3, max: 7 };
    const rest = { length: 'short', minutes: 30, rested: true, reason: null, rolls: [4], before: 10, after: 10, max_hp: 10, resources: [mana] };
    const used = { entry_id: 'up', name: '물약', used: true, reason: null, target: null, remaining: 1, cured: [], injured: [], resources: [mana] };
    expect(restLine(rest as unknown as Extract<Outcome, { rest: unknown }>['rest'])).toBe('HP 10 → 10 · 마나 1 → 3/7');
    expect(itemUseLine(used as never)).toBe('물약 사용(남은 1개) · 마나 1 → 3/7');
  });
});
